#!/usr/bin/env python3
"""Automated pattern extraction with fastsql database backend.

Provides workspace analysis, failure extraction, and pattern scoring.
"""

from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import argparse
import subprocess
import sys
import re

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db
    from lib.workspace import parse, list_workspaces as ws_list_workspaces, _get_active_campaign
    from lib.memory import add_failure, add_pattern, add_relationship, add_cross_relationship, get_stats, record_feedback_batch
    from lib.db.embeddings import similarity as semantic_similarity
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db
    from workspace import parse, list_workspaces as ws_list_workspaces, _get_active_campaign
    from memory import add_failure, add_pattern, add_relationship, add_cross_relationship, get_stats, record_feedback_batch
    from db.embeddings import similarity as semantic_similarity

# Note: Memory operations (add_failure, add_pattern, add_relationship) now handle
# their own locking internally using the shared db_write_lock from lib.db.locks


# =============================================================================
# Configuration Constants (Hardcoded Defaults)
# =============================================================================
# These thresholds control observer behavior. Documented here per Pass 6.

# Novelty threshold for scoring: entries with similarity > 0.7 to existing memory
# are NOT considered novel (no +1 score bonus)
#
# THRESHOLD DESIGN (intentional gap with DUPLICATE_THRESHOLD=0.85 in memory.py):
# - 0.00-0.70: Novel (gets +1 score bonus, added as new entry)
# - 0.71-0.84: Related but distinct (no bonus, added as separate entry)
# - 0.85-1.00: Duplicate (merged into existing entry)
#
# The 0.71-0.84 zone captures entries that are semantically related but
# sufficiently different to warrant separate storage without novelty bonus.
NOVELTY_THRESHOLD = 0.7

# Minimum score for pattern extraction (score_workspace must return >= 3)
MIN_PATTERN_SCORE = 3

# Note: All storage is now in .ftl/ftl.db
# WORKSPACE_DIR kept for API compatibility (ignored in actual operations)
WORKSPACE_DIR = None


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


# =============================================================================
# Workspace Listing (delegates to workspace module with campaign filtering)
# =============================================================================

def list_workspaces(workspace_dir: Path = WORKSPACE_DIR) -> dict:
    """Categorize workspaces by status, filtered to active campaign.

    Args:
        workspace_dir: Ignored (kept for API compatibility)

    Returns:
        {"complete": [dicts], "blocked": [dicts], "active": [dicts]}
    """
    campaign = _get_active_campaign()
    campaign_id = campaign["id"] if campaign else None

    all_ws = ws_list_workspaces(campaign_id=campaign_id)

    # Categorize for API compatibility
    workspaces = {"complete": [], "blocked": [], "active": []}
    for ws in all_ws:
        status = ws.get("status", "active")
        if status in workspaces:
            workspaces[status].append(ws)

    return workspaces


# =============================================================================
# Block Verification
# =============================================================================

def verify_block(workspace_path_or_id, timeout: int = 30) -> dict:
    """Verify if a blocked workspace is truly blocked by re-running verify.

    Args:
        workspace_path_or_id: Path, workspace_id, or workspace dict
        timeout: Verification timeout in seconds

    Returns:
        {"status": "CONFIRMED"|"FALSE_POSITIVE"|"ERROR", "reason": str, "output": str}
    """
    # Accept dict directly
    if isinstance(workspace_path_or_id, dict):
        ws = workspace_path_or_id
    else:
        try:
            ws = parse(workspace_path_or_id)
        except Exception as e:
            return {"status": "ERROR", "reason": f"Parse error: {e}", "output": ""}

    verify_cmd = ws.get("verify", "")
    if not verify_cmd:
        return {"status": "CONFIRMED", "reason": "No verify command", "output": ""}

    try:
        result = subprocess.run(
            verify_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )

        output = result.stdout + result.stderr
        has_error = any(x in output.upper() for x in ["FAIL", "ERROR", "EXCEPTION"])

        if result.returncode == 0 and not has_error:
            return {"status": "FALSE_POSITIVE", "reason": "Tests pass now", "output": output}
        elif result.returncode == 0 and has_error:
            return {"status": "CONFIRMED", "reason": "Exit 0 but output contains errors", "output": output}
        else:
            return {"status": "CONFIRMED", "reason": f"exit {result.returncode}", "output": output}

    except subprocess.TimeoutExpired:
        # Timeout should NOT be treated as confirmed - slow tests may still pass
        # Return INDETERMINATE so observer can handle appropriately
        return {"status": "INDETERMINATE", "reason": "Verify command timed out", "output": ""}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e), "output": ""}


# =============================================================================
# Workspace Scoring
# =============================================================================

def score_workspace(workspace_path_or_id, memory: dict = None) -> dict:
    """Score a completed workspace for pattern extraction.

    Scoring rules:
    - Was blocked then fixed: +3
    - Clean first-try success: +2
    - Framework idiom applied: +2
    - Budget efficient (<50%): +1
    - Multi-file delta: +1
    - Novel (trigger not in memory): +1

    Returns:
        {"score": int, "breakdown": dict, "workspace": dict}
    """
    if memory is None:
        memory = {"failures": [], "patterns": []}

    # Accept dict directly
    if isinstance(workspace_path_or_id, dict):
        ws = workspace_path_or_id
    else:
        ws = parse(workspace_path_or_id)
    score = 0
    breakdown = {}

    # Check if was blocked then fixed
    db = _ensure_db()
    workspaces = db.t.workspace

    seq = ws.get("id", "").split("-")[0] if ws.get("id") else ""
    was_blocked = False
    if seq:
        blocked = list(workspaces.rows_where(
            "seq = ? AND status = ?",
            [seq, "blocked"]
        ))
        was_blocked = len(blocked) > 0

    if was_blocked:
        score += 3
        breakdown["blocked_then_fixed"] = 3

    # Clean first-try success
    delivered = ws.get("delivered", "").lower()
    retry_patterns = ["retry", "retried", "tried again", "second attempt", "multiple attempt", "failed then"]
    has_retry = any(pattern in delivered for pattern in retry_patterns)
    if not has_retry:
        score += 2
        breakdown["first_try_success"] = 2

    # Framework idiom applied
    idioms = ws.get("idioms", {})
    if idioms and idioms.get("required"):
        score += 2
        breakdown["framework_idioms"] = 2

    # Budget efficient
    budget = ws.get("budget", 5)
    if budget >= 4:
        score += 1
        breakdown["budget_efficient"] = 1

    # Multi-file delta
    delta = ws.get("delta", [])
    if len(delta) >= 2:
        score += 1
        breakdown["multi_file"] = 1

    # Novel approach
    objective = ws.get("objective", "")
    # Skip novelty check if memory is empty
    is_novel = True
    if memory.get("failures") or memory.get("patterns"):
        existing_triggers = {f.get("trigger", "") for f in memory.get("failures", [])}
        existing_triggers.update(p.get("trigger", "") for p in memory.get("patterns", []))
        is_novel = not any(
            semantic_similarity(objective, t) > NOVELTY_THRESHOLD for t in existing_triggers if t
        )

    if is_novel:
        score += 1
        breakdown["novel"] = 1

    return {"score": score, "breakdown": breakdown, "workspace": ws}


# =============================================================================
# Failure/Pattern Extraction
# =============================================================================

def extract_failure(workspace_path_or_id, verify_output: str = "") -> dict:
    """Extract failure entry from a blocked workspace.

    Returns:
        Failure dict ready for add_failure()
    """
    # Accept dict directly
    if isinstance(workspace_path_or_id, dict):
        ws = workspace_path_or_id
    else:
        ws = parse(workspace_path_or_id)
    delivered = ws.get("delivered", "")

    # Extract error from BLOCKED: prefix
    trigger = ""
    if "BLOCKED:" in delivered:
        trigger = delivered.split("BLOCKED:", 1)[1].strip().split("\n")[0]
    elif verify_output:
        for line in verify_output.split("\n"):
            if any(x in line.upper() for x in ["ERROR", "FAIL", "EXCEPTION"]):
                trigger = line.strip()
                break

    if not trigger:
        trigger = delivered[:100] if delivered else "Unknown error"

    name = _slugify(trigger[:50])

    # Extract fix hint
    fix = "UNKNOWN"
    if "Tried:" in delivered:
        tried = delivered.split("Tried:")[1].split("Unknown:")[0].strip()
        if tried:
            fix = f"Attempted: {tried[:200]}"

    budget = ws.get("budget", 5)

    return {
        "name": name,
        "trigger": trigger,
        "fix": fix,
        "match": _generalize_to_regex(trigger),
        "cost": budget * 1000,
        "source": [ws.get("id", ws.get("workspace_id", ""))],
    }


def extract_pattern(workspace_path_or_id, score_data: dict) -> dict:
    """Extract pattern entry from a high-scoring workspace.

    Returns:
        Pattern dict ready for add_pattern()
    """
    ws = score_data["workspace"]
    delivered = ws.get("delivered", "")
    objective = ws.get("objective", "")

    trigger = objective if objective else ws.get("id", "").replace("-", " ")
    insight = delivered[:300] if delivered else "Successful implementation"

    breakdown = score_data["breakdown"]
    if breakdown:
        insight_parts = [
            ("blocked_then_fixed", "Recovered from block"),
            ("first_try_success", "First-try success"),
            ("framework_idioms", "Used framework idioms"),
            ("budget_efficient", "Under budget"),
            ("multi_file", "Cross-file coordination"),
            ("novel", "Novel approach"),
        ]
        parts = [desc for key, desc in insight_parts if key in breakdown]
        if parts:
            insight = f"{', '.join(parts)}. {insight}"

    budget = ws.get("budget", 5)

    return {
        "name": ws.get("workspace_id", ws.get("id", _slugify(trigger[:30]))),
        "trigger": trigger,
        "insight": insight[:500],
        "saved": budget * 500,
        "source": [ws.get("id", ws.get("workspace_id", ""))],
    }


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')[:40]


def _generalize_to_regex(trigger: str) -> str:
    """Generalize trigger to regex pattern.

    Replaces quoted strings and digit sequences with regex wildcards
    to enable matching similar but not identical error messages.

    Handles escaped quotes within strings (e.g., "foo\"bar" or 'foo\'bar').
    Whitespace is normalized to allow flexible matching (fixes over-escaping issue).
    """
    # Use placeholders to handle escaping correctly
    placeholder_sq = "\x00SQ\x00"  # Single-quoted string placeholder
    placeholder_dq = "\x00DQ\x00"  # Double-quoted string placeholder
    placeholder_num = "\x00NUM\x00"  # Digit sequence placeholder
    placeholder_ws = "\x00WS\x00"  # Whitespace placeholder

    # Replace patterns BEFORE escaping (work on original trigger)
    # Use patterns that handle escaped quotes: match either non-quote/non-backslash,
    # or a backslash followed by any character (including escaped quotes)
    generalized = re.sub(r"'(?:[^'\\]|\\.)*'", placeholder_sq, trigger)
    generalized = re.sub(r'"(?:[^"\\]|\\.)*"', placeholder_dq, generalized)
    generalized = re.sub(r'\d+', placeholder_num, generalized)
    # Normalize whitespace sequences to placeholder BEFORE escaping
    generalized = re.sub(r'\s+', placeholder_ws, generalized)

    # Escape remaining special regex characters
    pattern = re.escape(generalized)

    # Restore placeholders with actual regex patterns
    pattern = pattern.replace(placeholder_sq, ".*")
    pattern = pattern.replace(placeholder_dq, ".*")
    pattern = pattern.replace(placeholder_num, r"\d+")
    pattern = pattern.replace(placeholder_ws, r"\s+")  # Match flexible whitespace

    return pattern


# =============================================================================
# Analysis
# =============================================================================

def analyze(
    workspace_dir: Path = WORKSPACE_DIR,
    verify_blocks: bool = True,
    max_workers: int = 4
) -> dict:
    """Analyze all workspaces and extract patterns/failures.

    Returns:
        Analysis results with extracted failures and patterns
    """
    workspaces = list_workspaces(workspace_dir)

    result = {
        "workspaces": {
            "complete": len(workspaces["complete"]),
            "blocked": len(workspaces["blocked"]),
            "active": len(workspaces["active"]),
        },
        "verified": [],
        "failures_extracted": [],
        "patterns_extracted": [],
        "relationships_added": 0,
    }

    campaign_failures = []

    # Process blocked workspaces
    if verify_blocks and workspaces["blocked"]:
        verified_results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ws = {
                executor.submit(verify_block, ws["workspace_id"]): ws
                for ws in workspaces["blocked"]
            }
            for future in as_completed(future_to_ws):
                ws = future_to_ws[future]
                try:
                    verification = future.result()
                    verified_results[ws["workspace_id"]] = verification
                    result["verified"].append({
                        "workspace": ws["workspace_id"],
                        "status": verification["status"],
                        "reason": verification["reason"],
                    })
                except Exception as e:
                    result["verified"].append({
                        "workspace": ws["workspace_id"],
                        "status": "ERROR",
                        "reason": str(e),
                    })
                    verified_results[ws["workspace_id"]] = {"status": "ERROR", "output": ""}

        for ws in workspaces["blocked"]:
            verification = verified_results.get(ws["workspace_id"], {})
            # DESIGN DECISION: Only extract failures from CONFIRMED blocks.
            # INDETERMINATE (timeout) blocks are NOT treated as failures because:
            #   1. Slow tests may pass on retry with more time
            #   2. Recording timeouts as failures would pollute memory with transient issues
            #   3. True failures will eventually be CONFIRMED on re-run
            # FALSE_POSITIVE blocks are also skipped as verification proved them non-blocking.
            if verification.get("status") not in ["CONFIRMED"]:
                continue

            verify_output = verification.get("output", "")
            failure = extract_failure(ws["workspace_id"], verify_output)
            # Note: add_failure() handles its own locking internally
            add_result = add_failure(failure)
            result["failures_extracted"].append({
                "name": failure["name"],
                "result": add_result,
            })

            if add_result == "added":
                campaign_failures.append(failure["name"])
    else:
        for ws in workspaces["blocked"]:
            failure = extract_failure(ws["workspace_id"], "")
            # Note: add_failure() handles its own locking internally
            add_result = add_failure(failure)
            result["failures_extracted"].append({
                "name": failure["name"],
                "result": add_result,
            })

            if add_result == "added":
                campaign_failures.append(failure["name"])

    # Process completed workspaces
    for ws in workspaces["complete"]:
        score_data = score_workspace(ws["workspace_id"])

        if score_data["score"] >= MIN_PATTERN_SCORE:
            pattern = extract_pattern(ws["workspace_id"], score_data)
            # Note: add_pattern() handles its own locking internally
            add_result = add_pattern(pattern)
            result["patterns_extracted"].append({
                "name": pattern["name"],
                "score": score_data["score"],
                "breakdown": score_data["breakdown"],
                "result": add_result,
            })

            if "blocked_then_fixed" in score_data["breakdown"] and add_result == "added":
                seq = score_data["workspace"].get("id", "").split("-")[0]
                for failure_info in result["failures_extracted"]:
                    if failure_info["name"].startswith(seq) or seq in failure_info.get("name", ""):
                        # Note: add_cross_relationship() handles db operations internally
                        cross_result = add_cross_relationship(
                            failure_info["name"],
                            pattern["name"],
                            "solves"
                        )
                        if cross_result == "added":
                            result["relationships_added"] += 1
                        break

    # Close learning loop: record feedback for utilized memories
    result["feedback_recorded"] = {"helped": 0, "not_helped": 0}
    for ws in workspaces["complete"]:
        ws_data = parse(ws["workspace_id"]) if isinstance(ws, dict) else parse(ws)
        if "error" in ws_data:
            continue

        # Get utilized memories from workspace completion
        utilized = ws_data.get("utilized_memories", [])
        if not utilized:
            continue

        # Get injected memories from prior_knowledge
        prior_knowledge = ws_data.get("prior_knowledge", {})
        injected = []
        for f in prior_knowledge.get("failures", []):
            if f.get("name"):
                injected.append({"name": f["name"], "type": "failure"})
        for p in prior_knowledge.get("patterns", []):
            if p.get("name"):
                injected.append({"name": p["name"], "type": "pattern"})
        for sf in prior_knowledge.get("sibling_failures", []):
            if sf.get("name"):
                injected.append({"name": sf["name"], "type": "failure"})

        if injected:
            feedback_result = record_feedback_batch(utilized, injected)
            result["feedback_recorded"]["helped"] += feedback_result.get("helped", 0)
            result["feedback_recorded"]["not_helped"] += feedback_result.get("not_helped", 0)

    # Link co-occurring failures
    for i, f1 in enumerate(campaign_failures):
        for f2 in campaign_failures[i+1:]:
            # Note: add_relationship() uses transactions internally
            rel_result = add_relationship(f1, f2, "failure")
            if rel_result == "added":
                result["relationships_added"] += 1

    return result


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL observer - automated pattern extraction")
    subparsers = parser.add_subparsers(dest="command")

    # analyze command
    a = subparsers.add_parser("analyze", help="Analyze all workspaces")
    a.add_argument("--workspace-dir", help="Workspace directory path (ignored)")
    a.add_argument("--no-verify", action="store_true", help="Skip block verification")

    # verify-blocks command
    vb = subparsers.add_parser("verify-blocks", help="Verify all blocked workspaces")
    vb.add_argument("--workspace-dir", help="Workspace directory path (ignored)")

    # score command
    s = subparsers.add_parser("score", help="Score a single workspace")
    s.add_argument("path", help="Path to workspace or workspace_id")

    # extract-failure command
    ef = subparsers.add_parser("extract-failure", help="Extract failure from blocked workspace")
    ef.add_argument("path", help="Path to workspace or workspace_id")

    # list command
    lst = subparsers.add_parser("list", help="List workspaces by status")

    args = parser.parse_args()

    if args.command == "analyze":
        result = analyze(verify_blocks=not args.no_verify)
        print(json.dumps(result, indent=2))

    elif args.command == "verify-blocks":
        workspaces = list_workspaces()
        results = []
        for ws in workspaces["blocked"]:
            verification = verify_block(ws["workspace_id"])
            results.append({
                "workspace": ws["workspace_id"],
                **verification
            })
        print(json.dumps(results, indent=2))

    elif args.command == "score":
        result = score_workspace(args.path)
        print(json.dumps(result, indent=2))

    elif args.command == "extract-failure":
        result = extract_failure(args.path)
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        result = list_workspaces()
        print(json.dumps({
            "complete": len(result["complete"]),
            "blocked": len(result["blocked"]),
            "active": len(result["active"]),
        }, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
