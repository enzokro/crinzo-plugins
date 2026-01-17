#!/usr/bin/env python3
"""Automated pattern extraction from completed workspaces."""

from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import argparse
import subprocess
import sys

# Support both standalone execution and module import
try:
    from lib.workspace import parse, WORKSPACE_DIR
    from lib.memory import load_memory, add_failure, add_pattern, add_relationship, add_cross_relationship
    from lib.embeddings import similarity as semantic_similarity
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from workspace import parse, WORKSPACE_DIR
    from memory import load_memory, add_failure, add_pattern, add_relationship, add_cross_relationship
    from embeddings import similarity as semantic_similarity


def list_workspaces(
    workspace_dir: Path = WORKSPACE_DIR,
    max_age_days: int = None
) -> dict:
    """Categorize workspaces by status with optional age filtering.

    Args:
        workspace_dir: Path to workspace directory
        max_age_days: Only include workspaces modified within this many days (None = no filter)

    Returns:
        {"complete": [paths], "blocked": [paths], "active": [paths]}
    """
    result = {"complete": [], "blocked": [], "active": []}
    if not workspace_dir.exists():
        return result

    cutoff_time = None
    if max_age_days is not None:
        cutoff_time = datetime.now() - timedelta(days=max_age_days)

    for p in workspace_dir.glob("*.xml"):
        # Apply age filter if specified
        if cutoff_time is not None:
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            if mtime < cutoff_time:
                continue

        if "_complete.xml" in p.name:
            result["complete"].append(p)
        elif "_blocked.xml" in p.name:
            result["blocked"].append(p)
        elif "_active.xml" in p.name:
            result["active"].append(p)

    return result


def verify_block(workspace_path: Path, timeout: int = 30) -> dict:
    """Verify if a blocked workspace is truly blocked by re-running verify.

    Returns:
        {"status": "CONFIRMED"|"FALSE_POSITIVE", "reason": str, "output": str}
    """
    try:
        ws = parse(workspace_path)
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
        else:
            return {"status": "CONFIRMED", "reason": f"exit {result.returncode}", "output": output}

    except subprocess.TimeoutExpired:
        return {"status": "CONFIRMED", "reason": "Timeout", "output": ""}
    except Exception as e:
        return {"status": "ERROR", "reason": str(e), "output": ""}


def score_workspace(workspace_path: Path, memory: dict = None) -> dict:
    """Score a completed workspace for pattern extraction.

    Scoring rules (from observer.md):
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
        memory = load_memory()

    ws = parse(workspace_path)
    score = 0
    breakdown = {}

    # Check if this task was blocked then fixed (slug appears in both blocked and complete)
    workspace_dir = workspace_path.parent
    slug = workspace_path.stem.replace("_complete", "")
    blocked_path = workspace_dir / f"{slug}_blocked.xml"

    # Actually check for any blocked workspace with same seq
    seq = ws.get("id", "").split("-")[0] if ws.get("id") else ""
    was_blocked = any(
        p.stem.startswith(seq) for p in workspace_dir.glob("*_blocked.xml")
    ) if seq else False

    if was_blocked:
        score += 3
        breakdown["blocked_then_fixed"] = 3

    # Clean first-try success (no retry/failure patterns in delivered)
    delivered = ws.get("delivered", "").lower()
    # Negative patterns that indicate retries/failures
    retry_patterns = ["retry", "retried", "tried again", "second attempt", "multiple attempt", "failed then"]
    has_retry = any(pattern in delivered for pattern in retry_patterns)
    if not has_retry:
        score += 2
        breakdown["first_try_success"] = 2

    # Framework idiom applied
    if ws.get("idioms") and ws["idioms"].get("required"):
        score += 2
        breakdown["framework_idioms"] = 2

    # Budget efficient (<50% used)
    budget = ws.get("budget", 5)
    # Estimate tools used from delivered text (rough heuristic)
    # In practice, this should be tracked explicitly
    if budget >= 4:  # Assume efficient if budget was generous
        score += 1
        breakdown["budget_efficient"] = 1

    # Multi-file delta
    delta = ws.get("delta", [])
    if len(delta) >= 2:
        score += 1
        breakdown["multi_file"] = 1

    # Novel approach (trigger not in existing memory)
    existing_triggers = {f.get("trigger", "") for f in memory.get("failures", [])}
    existing_triggers.update(p.get("trigger", "") for p in memory.get("patterns", []))

    # Check if objective or key aspects are novel
    objective = ws.get("objective", "")
    is_novel = not any(
        _similarity(objective, t) > 0.7 for t in existing_triggers if t
    )
    if is_novel:
        score += 1
        breakdown["novel"] = 1

    return {"score": score, "breakdown": breakdown, "workspace": ws, "path": str(workspace_path)}


def _similarity(a: str, b: str) -> float:
    """Similarity check using semantic embeddings when available.

    Falls back to SequenceMatcher if embeddings unavailable.
    """
    return semantic_similarity(a, b)


def extract_failure(workspace_path: Path, verify_output: str = "") -> dict:
    """Extract failure entry from a blocked workspace.

    Returns:
        Failure dict ready for add_failure()
    """
    ws = parse(workspace_path)
    delivered = ws.get("delivered", "")

    # Extract error from BLOCKED: prefix
    trigger = ""
    if "BLOCKED:" in delivered:
        trigger = delivered.split("BLOCKED:", 1)[1].strip().split("\n")[0]
    elif verify_output:
        # Take first error line from verify output
        for line in verify_output.split("\n"):
            if any(x in line.upper() for x in ["ERROR", "FAIL", "EXCEPTION"]):
                trigger = line.strip()
                break

    if not trigger:
        trigger = delivered[:100] if delivered else "Unknown error"

    # Generate name from trigger
    name = _slugify(trigger[:50])

    # Extract fix hint from "Tried" section if present
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
        "source": [ws.get("id", workspace_path.stem)],
    }


def extract_pattern(workspace_path: Path, score_data: dict) -> dict:
    """Extract pattern entry from a high-scoring workspace.

    Returns:
        Pattern dict ready for add_pattern()
    """
    ws = score_data["workspace"]
    delivered = ws.get("delivered", "")
    objective = ws.get("objective", "")

    # Pattern trigger is the objective/task type
    trigger = objective if objective else ws.get("id", "").replace("-", " ")

    # Insight from delivered summary
    insight = delivered[:300] if delivered else "Successful implementation"

    # Enhance with score breakdown
    breakdown = score_data["breakdown"]
    if breakdown:
        insight_parts = []
        if "blocked_then_fixed" in breakdown:
            insight_parts.append("Recovered from block")
        if "first_try_success" in breakdown:
            insight_parts.append("First-try success")
        if "framework_idioms" in breakdown:
            insight_parts.append("Used framework idioms")
        if insight_parts:
            insight = f"{', '.join(insight_parts)}. {insight}"

    budget = ws.get("budget", 5)

    return {
        "name": _slugify(trigger[:30]),
        "trigger": trigger,
        "insight": insight[:500],
        "saved": budget * 500,
        "source": [ws.get("id", workspace_path.stem)],
    }


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    import re
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s_]+', '-', text)
    text = re.sub(r'-+', '-', text)
    return text.strip('-')[:40]


def _generalize_to_regex(trigger: str) -> str:
    """Generalize trigger to regex pattern."""
    import re
    # Escape special chars, replace common variable parts
    pattern = re.escape(trigger)
    # Replace quoted strings with wildcard
    pattern = re.sub(r"\\'[^']*\\'", ".*", pattern)
    pattern = re.sub(r'\\"[^"]*\\"', ".*", pattern)
    # Replace numbers with digit pattern
    pattern = re.sub(r'\d+', r'\\d+', pattern)
    return pattern


def analyze(
    workspace_dir: Path = WORKSPACE_DIR,
    verify_blocks: bool = True,
    max_workers: int = 4
) -> dict:
    """Analyze all workspaces and extract patterns/failures.

    Args:
        workspace_dir: Path to workspace directory
        verify_blocks: Whether to verify blocked workspaces by re-running verify
        max_workers: Maximum parallel workers for verification (default: 4)

    Returns:
        {
            "workspaces": {"complete": N, "blocked": M, "active": K},
            "verified": [{"workspace": str, "status": str, "reason": str}],
            "failures_extracted": [{"name": str, "result": str}],
            "patterns_extracted": [{"name": str, "result": str}],
            "relationships_added": N
        }
    """
    workspaces = list_workspaces(workspace_dir)
    memory = load_memory()

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

    # Track failures from this campaign for relationship linking
    campaign_failures = []

    # Process blocked workspaces with parallel verification
    if verify_blocks and workspaces["blocked"]:
        # Parallel verification using ThreadPoolExecutor
        verified_results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(verify_block, path): path
                for path in workspaces["blocked"]
            }
            for future in as_completed(future_to_path):
                blocked_path = future_to_path[future]
                try:
                    verification = future.result()
                    verified_results[blocked_path] = verification
                    result["verified"].append({
                        "workspace": blocked_path.stem,
                        "status": verification["status"],
                        "reason": verification["reason"],
                    })
                except Exception as e:
                    result["verified"].append({
                        "workspace": blocked_path.stem,
                        "status": "ERROR",
                        "reason": str(e),
                    })
                    verified_results[blocked_path] = {"status": "ERROR", "output": ""}

        # Extract failures from confirmed blocks
        for blocked_path in workspaces["blocked"]:
            verification = verified_results.get(blocked_path, {})
            if verification.get("status") != "CONFIRMED":
                continue

            verify_output = verification.get("output", "")
            failure = extract_failure(blocked_path, verify_output)
            add_result = add_failure(failure)
            result["failures_extracted"].append({
                "name": failure["name"],
                "result": add_result,
            })

            if add_result == "added":
                campaign_failures.append(failure["name"])
    else:
        # No verification - extract from all blocked workspaces
        for blocked_path in workspaces["blocked"]:
            failure = extract_failure(blocked_path, "")
            add_result = add_failure(failure)
            result["failures_extracted"].append({
                "name": failure["name"],
                "result": add_result,
            })

            if add_result == "added":
                campaign_failures.append(failure["name"])

    # Process completed workspaces
    for complete_path in workspaces["complete"]:
        score_data = score_workspace(complete_path, memory)

        if score_data["score"] >= 3:
            pattern = extract_pattern(complete_path, score_data)
            add_result = add_pattern(pattern)
            result["patterns_extracted"].append({
                "name": pattern["name"],
                "score": score_data["score"],
                "breakdown": score_data["breakdown"],
                "result": add_result,
            })

            # Cross-type relationship: If this was blocked-then-fixed,
            # link the pattern to the failure it solved
            if "blocked_then_fixed" in score_data["breakdown"] and add_result == "added":
                # Find the corresponding blocked failure
                seq = score_data["workspace"].get("id", "").split("-")[0]
                for failure_info in result["failures_extracted"]:
                    if failure_info["name"].startswith(seq) or seq in failure_info.get("name", ""):
                        cross_result = add_cross_relationship(
                            failure_info["name"],
                            pattern["name"],
                            "solves"
                        )
                        if cross_result == "added":
                            result["relationships_added"] += 1
                        break

    # Link co-occurring failures
    for i, f1 in enumerate(campaign_failures):
        for f2 in campaign_failures[i+1:]:
            rel_result = add_relationship(f1, f2, "failure")
            if rel_result == "added":
                result["relationships_added"] += 1

    return result


def main():
    parser = argparse.ArgumentParser(description="FTL observer - automated pattern extraction")
    subparsers = parser.add_subparsers(dest="command")

    # analyze command
    a = subparsers.add_parser("analyze", help="Analyze all workspaces")
    a.add_argument("--workspace-dir", help="Workspace directory path")
    a.add_argument("--no-verify", action="store_true", help="Skip block verification")

    # verify-blocks command
    vb = subparsers.add_parser("verify-blocks", help="Verify all blocked workspaces")
    vb.add_argument("--workspace-dir", help="Workspace directory path")

    # score command
    s = subparsers.add_parser("score", help="Score a single workspace")
    s.add_argument("path", help="Path to workspace XML")

    # extract-failure command
    ef = subparsers.add_parser("extract-failure", help="Extract failure from blocked workspace")
    ef.add_argument("path", help="Path to blocked workspace XML")

    args = parser.parse_args()

    if args.command == "analyze":
        workspace_dir = Path(args.workspace_dir) if args.workspace_dir else WORKSPACE_DIR
        result = analyze(workspace_dir, verify_blocks=not args.no_verify)
        print(json.dumps(result, indent=2))

    elif args.command == "verify-blocks":
        workspace_dir = Path(args.workspace_dir) if args.workspace_dir else WORKSPACE_DIR
        workspaces = list_workspaces(workspace_dir)
        results = []
        for blocked_path in workspaces["blocked"]:
            verification = verify_block(blocked_path)
            results.append({
                "workspace": blocked_path.stem,
                **verification
            })
        print(json.dumps(results, indent=2))

    elif args.command == "score":
        path = Path(args.path)
        result = score_workspace(path)
        print(json.dumps(result, indent=2))

    elif args.command == "extract-failure":
        path = Path(args.path)
        result = extract_failure(path)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
