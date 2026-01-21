#!/usr/bin/env python3
"""Exploration aggregation and storage with fastsql database backend.

Provides explorer output aggregation, storage, and retrieval.
"""

from pathlib import Path
from datetime import datetime
import json
import argparse
import logging
import sys
import subprocess
import re

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, Exploration
    from lib.db.schema import ExplorerResult
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db, Exploration
    from db.schema import ExplorerResult

# Maximum JSON size to parse (1MB)
MAX_JSON_SIZE = 1024 * 1024

# Git SHA timeout in seconds (configurable via environment)
import os
GIT_SHA_TIMEOUT = int(os.environ.get("FTL_GIT_SHA_TIMEOUT", "5"))

# Valid explorer modes
EXPLORER_MODES = {"structure", "pattern", "memory", "delta"}

# Schema coercion rules: transform data to expected types
COERCIONS = {
    "structure": {
        "directories": lambda v: {str(d): True for d in v} if isinstance(v, list) else v,
    },
    "pattern": {
        "framework": lambda v: str(v) if v is not None else None,
        "confidence": lambda v: float(v) if v is not None else 0.5,
    },
    "delta": {
        "candidates": lambda v: list(v) if hasattr(v, '__iter__') and not isinstance(v, (str, dict)) else [v] if v else [],
    },
    "memory": {},
}

# Default values for missing fields
DEFAULTS = {
    "structure": {"directories": {}, "entry_points": [], "test_patterns": [], "config_files": []},
    "pattern": {"framework": None, "confidence": 0.5, "idioms": {"required": [], "forbidden": []}},
    "memory": {"relevant_failures": [], "relevant_patterns": [], "similar_campaigns": []},
    "delta": {"candidates": [], "candidate_files": []},
}


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def _get_active_campaign():
    """Get active campaign from database."""
    db = _ensure_db()
    campaigns = db.t.campaign
    rows = list(campaigns.rows_where("status = ?", ["active"]))
    if rows:
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[0]
    return None


# =============================================================================
# JSON Extraction Helpers
# =============================================================================

def extract_json(text: str, max_size: int = MAX_JSON_SIZE) -> dict | None:
    """Extract JSON from text that may contain extra content."""
    if not text:
        return None

    text = text.strip()

    if len(text) > max_size:
        return None

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Remove markdown code blocks
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Find JSON object pattern
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try any { ... } pattern
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end > brace_start:
        potential_json = text[brace_start:brace_end + 1]
        try:
            return json.loads(potential_json)
        except json.JSONDecodeError:
            pass

    return None


def validate_result(result: dict, strict: bool = True) -> tuple:
    """Validate and coerce explorer result to expected schema.

    Applies schema coercion (type transforms) and defaults for missing fields.
    Validates common fields (mode, status) are present and valid.
    Mode-specific fields are enforced when strict=True and status is ok/partial.

    Args:
        result: Explorer result dict to validate (MUTATED by coercion)
        strict: If True, reject missing mode-specific fields for ok/partial status

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(result, dict):
        return False, "Result is not a dict"

    mode = result.get("mode")
    if not mode:
        return False, "Missing required field: mode"
    if mode not in EXPLORER_MODES:
        return False, f"Invalid mode: {mode}"

    if "status" not in result:
        return False, "Missing required field: status"

    status = result.get("status", "")

    # Apply defaults for missing fields (mutates result)
    if mode in DEFAULTS:
        for field, default in DEFAULTS[mode].items():
            if field not in result:
                result[field] = default
                logging.debug(f"Mode {mode}: applied default for '{field}'")

    # BUG FIX: For pattern mode, derive top-level confidence from frameworks array
    # if still at default (0.5). Explorers emit confidence inside frameworks[0].
    if mode == "pattern" and result.get("confidence") == 0.5:
        frameworks = result.get("frameworks", [])
        if frameworks and isinstance(frameworks, list) and len(frameworks) > 0:
            first_fw = frameworks[0]
            if isinstance(first_fw, dict) and "confidence" in first_fw:
                result["confidence"] = float(first_fw["confidence"])
                logging.debug(f"Mode pattern: derived confidence {result['confidence']} from frameworks[0]")

    # Apply coercions for type mismatches (mutates result)
    if mode in COERCIONS:
        for field, coerce_fn in COERCIONS[mode].items():
            if field in result:
                try:
                    original = result[field]
                    result[field] = coerce_fn(original)
                    if result[field] != original:
                        logging.debug(f"Mode {mode}: coerced '{field}' from {type(original).__name__} to {type(result[field]).__name__}")
                except Exception as e:
                    logging.warning(f"Mode {mode}: coercion failed for '{field}': {e}")

    # Mode-specific field type validation (applies to all statuses, after coercion)
    mode_field_types = {
        "structure": {"directories": dict},
        "pattern": {"framework": (str, type(None)), "confidence": (int, float)},
        "delta": {"candidates": list},
        "memory": {},
    }

    # Validate types for mode-specific fields (after coercion applied)
    for field, expected_type in mode_field_types.get(mode, {}).items():
        if field in result and result[field] is not None:
            if not isinstance(result[field], expected_type):
                return False, f"Mode {mode} field '{field}' has wrong type after coercion: expected {expected_type}, got {type(result[field]).__name__}"

    # Mode-specific presence validation (only for ok/partial status)
    if status in ("ok", "partial"):
        mode_requirements = {
            "structure": ["directories"],
            "pattern": [],  # framework can be None, confidence has default
            "delta": ["candidates"],
            "memory": [],
        }
        missing = [f for f in mode_requirements.get(mode, []) if f not in result]
        if missing:
            if strict:
                return False, f"Mode {mode} missing required fields: {missing}"
            else:
                logging.debug(f"Mode {mode} missing recommended fields: {missing}")

    return True, ""


# =============================================================================
# Core Exploration Operations
# =============================================================================

def aggregate(results: list, objective: str = None) -> dict:
    """Combine explorer outputs into single exploration dict.

    Args:
        results: List of explorer output dicts
        objective: Original objective text

    Returns:
        Combined exploration dict
    """
    # Get git sha (timeout configurable via FTL_GIT_SHA_TIMEOUT env var)
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_SHA_TIMEOUT
        ).stdout.strip()
    except Exception:
        git_sha = "unknown"

    exploration = {
        "_meta": {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "git_sha": git_sha,
            "objective": objective,
        }
    }

    seen_modes = set()
    status_priority = {"ok": 3, "partial": 2, "error": 1, "unknown": 0}

    for r in results:
        is_valid, error = validate_result(r, strict=False)
        if not is_valid:
            mode = r.get("mode", "unknown") if isinstance(r, dict) else "invalid"
            # Only drop if fundamentally malformed (not dict, no mode, invalid mode)
            if not isinstance(r, dict) or "mode" not in r or r.get("mode") not in EXPLORER_MODES:
                logging.warning(f"Dropping malformed explorer result for mode '{mode}': {error}")
                continue
            # Otherwise warn but continue with coerced/defaulted data
            logging.warning(f"Explorer result for mode '{mode}' has issues (continuing with coerced data): {error}")

        mode = r["mode"]
        status = r.get("status", "unknown")

        if mode in seen_modes:
            existing = exploration.get(mode, {})
            existing_status = existing.get("status", "unknown")
            new_priority = status_priority.get(status, 0)
            old_priority = status_priority.get(existing_status, 0)

            # Only replace if strictly better status, or same status but new has valid content
            if new_priority < old_priority:
                continue
            if new_priority == old_priority:
                # Same status: prefer result with valid mode-specific content
                new_valid, _ = validate_result(r, strict=True)
                old_valid, _ = validate_result(existing, strict=True)
                if old_valid and not new_valid:
                    continue  # Keep existing valid result

        seen_modes.add(mode)

        if status in ["ok", "partial"]:
            exploration[mode] = r
        else:
            # Preserve partial data even on error - don't discard mode-specific fields
            error_entry = {
                "mode": mode,
                "status": "error",
                "_error": r.get("error", "unknown error")
            }
            # Copy any mode-specific data that was provided despite error status
            for key in ["directories", "framework", "confidence", "candidates", "idioms"]:
                if key in r:
                    error_entry[key] = r[key]
            exploration[mode] = error_entry

    return exploration


# =============================================================================
# Session-Based Explorer Operations
# =============================================================================

def write_result(session_id: str, mode: str, result: dict) -> dict:
    """Write individual explorer result to database.

    Args:
        session_id: UUID linking parallel explorers
        mode: Explorer mode (structure|pattern|memory|delta)
        result: Explorer output dict

    Returns:
        {"session_id": session_id, "mode": mode, "status": "written"}
    """
    db = _ensure_db()

    # Apply defaults in write path for consistency
    # Pattern mode: confidence defaults to 0.5 (neutral/unknown) if not specified
    if mode == "pattern" and "confidence" not in result:
        result = dict(result)  # Don't mutate input
        result["confidence"] = 0.5

    er = ExplorerResult(
        session_id=session_id,
        mode=mode,
        status=result.get("status", "ok"),
        result=json.dumps(result),
        created_at=datetime.now().isoformat()
    )
    db.t.explorer_result.insert(er)
    return {"session_id": session_id, "mode": mode, "status": "written"}


def get_session_status(session_id: str) -> dict:
    """Get completion status for exploration session.

    Args:
        session_id: UUID linking parallel explorers

    Returns:
        {"completed": [...], "missing": [...], "total": N, "quorum_met": bool}
    """
    db = _ensure_db()
    rows = list(db.t.explorer_result.rows_where(
        "session_id = ?", [session_id]
    ))
    completed = [r["mode"] for r in rows if r["status"] in ["ok", "partial", "error"]]
    missing = [m for m in ["structure", "pattern", "memory", "delta"] if m not in completed]
    return {
        "completed": completed,
        "missing": missing,
        "total": len(completed),
        "quorum_met": len(completed) >= 3
    }


def aggregate_session(session_id: str, objective: str = None) -> dict:
    """Aggregate explorer results from database session.

    Args:
        session_id: UUID linking parallel explorers
        objective: Original objective text

    Returns:
        Combined exploration dict
    """
    db = _ensure_db()
    rows = list(db.t.explorer_result.rows_where(
        "session_id = ?", [session_id]
    ))
    results = [json.loads(r["result"]) for r in rows]
    return aggregate(results, objective)


def clear_session(session_id: str) -> dict:
    """Delete explorer results for a session.

    Args:
        session_id: UUID to clear

    Returns:
        {"cleared": count}
    """
    db = _ensure_db()
    rows = list(db.t.explorer_result.rows_where("session_id = ?", [session_id]))
    for row in rows:
        db.t.explorer_result.delete(row["id"])
    return {"cleared": len(rows)}


# =============================================================================
# Core Exploration Write/Read Operations
# =============================================================================

def write(exploration: dict, require_campaign: bool = False) -> dict:
    """Write exploration to database.

    Args:
        exploration: Aggregated exploration dict
        require_campaign: If True (default), raise error if no active campaign

    Returns:
        {"id": exploration_id} or {"error": str} if no campaign and required
    """
    db = _ensure_db()
    explorations = db.t.exploration
    campaign = _get_active_campaign()

    if require_campaign and not campaign:
        return {"error": "No active campaign. Exploration would be orphaned.", "id": None}

    meta = exploration.get("_meta", {})

    exp = Exploration(
        campaign_id=campaign["id"] if campaign else None,
        objective=meta.get("objective", ""),
        git_sha=meta.get("git_sha", ""),
        created_at=datetime.now().isoformat(),
        structure=json.dumps(exploration.get("structure", {})),
        pattern=json.dumps(exploration.get("pattern", {})),
        memory=json.dumps(exploration.get("memory", {})),
        delta=json.dumps(exploration.get("delta", {})),
        modes_completed=sum(1 for k in ["structure", "pattern", "memory", "delta"]
                          if exploration.get(k, {}).get("status") in ["ok", "partial"]),
        status="complete"
    )

    result = explorations.insert(exp)

    return {"id": result.id}


def read(campaign_id: int = None) -> dict | None:
    """Read latest exploration from database.

    Args:
        campaign_id: Optional campaign ID to filter by. If not provided,
                     uses active campaign. If no active campaign, returns latest.

    Returns:
        Exploration dict or None
    """
    db = _ensure_db()
    explorations = db.t.exploration

    # Filter by campaign_id if provided, else use active campaign
    if campaign_id:
        rows = list(explorations.rows_where("campaign_id = ?", [campaign_id]))
    else:
        campaign = _get_active_campaign()
        if campaign:
            rows = list(explorations.rows_where("campaign_id = ?", [campaign["id"]]))
        else:
            rows = list(explorations.rows)

    if not rows:
        return None

    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    row = rows[0]

    return {
        "_meta": {
            "git_sha": row.get("git_sha", ""),
            "objective": row.get("objective", ""),
            "created_at": row.get("created_at", ""),
        },
        "structure": json.loads(row.get("structure") or "{}"),
        "pattern": json.loads(row.get("pattern") or "{}"),
        "memory": json.loads(row.get("memory") or "{}"),
        "delta": json.loads(row.get("delta") or "{}"),
    }


def clear() -> dict:
    """Clear exploration cache.

    Returns:
        {"cleared": count}
    """
    db = _ensure_db()
    explorations = db.t.exploration

    # Delete all explorations
    rows = list(explorations.rows)
    for row in rows:
        explorations.delete(row["id"])

    return {"cleared": len(rows)}


def get_structure() -> dict:
    """Get structure section from exploration."""
    exploration = read()
    if not exploration:
        return {"status": "missing"}
    structure = exploration.get("structure", {})
    if not structure:  # Handle empty dict case
        return {"status": "missing"}
    return structure


def get_pattern() -> dict:
    """Get pattern section from exploration.

    Returns:
        Pattern dict with framework, confidence, and idioms.

    Confidence Semantics (P7 Decision):
        - 0.0: Framework explicitly NOT detected (confident negative)
        - 0.5: Unknown/neutral (no pattern data or not specified) - DEFAULT
        - 1.0: Framework confidently detected

        The 0.5 default represents "insufficient data to determine" rather than
        "definitely no framework". This prevents false negatives when explorer
        data is missing or incomplete.
    """
    fallback = {
        "status": "missing",
        "framework": "none",
        "confidence": 0.5,  # Neutral: insufficient data (not confident negative)
        "idioms": {"required": [], "forbidden": []}
    }
    exploration = read()
    if not exploration:
        return fallback
    pattern = exploration.get("pattern", {})
    if not pattern:  # Handle empty dict case
        return fallback
    # Ensure confidence field exists - use 0.5 for neutral/unknown
    if "confidence" not in pattern:
        pattern["confidence"] = 0.5
    return pattern


def get_memory() -> dict:
    """Get memory section from exploration."""
    exploration = read()
    base = {
        "status": "missing",
        "failures": [],
        "patterns": [],
        "total_in_memory": {"failures": 0, "patterns": 0},
        "similar_campaigns": [],
    }

    if not exploration:
        return base

    memory = exploration.get("memory", base)

    # Augment with similar campaigns
    if "similar_campaigns" not in memory:
        try:
            from lib.campaign import find_similar
            # Threshold 0.5 per explorer.md MEMORY mode spec (line 79)
            similar = find_similar(threshold=0.5, max_results=3)
            memory["similar_campaigns"] = [
                {
                    "objective": s.get("objective", ""),
                    "similarity": s.get("similarity", 0),
                    "outcome": s.get("outcome", ""),
                    "patterns_from": s.get("patterns_from", []),
                }
                for s in similar
            ]
        except Exception as e:
            import logging
            logging.warning(f"Failed to find similar campaigns: {e}")
            memory["similar_campaigns"] = []

    return memory


def get_delta() -> dict:
    """Get delta section from exploration."""
    fallback = {"status": "missing", "candidates": []}
    exploration = read()
    if not exploration:
        return fallback
    delta = exploration.get("delta", {})
    if not delta:  # Handle empty dict case
        return fallback
    return delta


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL exploration operations")
    subparsers = parser.add_subparsers(dest="command")

    # Session-based commands
    wr = subparsers.add_parser("write-result", help="Write explorer result to database")
    wr.add_argument("--session", required=True, help="Session ID")
    wr.add_argument("--mode", required=True, help="Explorer mode")

    ss = subparsers.add_parser("session-status", help="Get session completion status")
    ss.add_argument("--session", required=True, help="Session ID")

    ags = subparsers.add_parser("aggregate-session", help="Aggregate session results")
    ags.add_argument("--session", required=True, help="Session ID")
    ags.add_argument("--objective", help="Original objective text")

    cs = subparsers.add_parser("clear-session", help="Clear session results")
    cs.add_argument("--session", required=True, help="Session ID")

    # aggregate command (from stdin)
    agg = subparsers.add_parser("aggregate", help="Aggregate explorer outputs from stdin")
    agg.add_argument("--objective", help="Original objective text")

    # write command
    subparsers.add_parser("write", help="Write exploration to database from stdin")

    # read command
    rd = subparsers.add_parser("read", help="Read latest exploration from database")
    rd.add_argument("--campaign-id", type=int, help="Filter by campaign ID")

    # get commands
    subparsers.add_parser("get-structure", help="Get structure section")
    subparsers.add_parser("get-pattern", help="Get pattern section")
    subparsers.add_parser("get-memory", help="Get memory section")
    subparsers.add_parser("get-delta", help="Get delta section")

    # clear command
    subparsers.add_parser("clear", help="Clear all explorations")

    args = parser.parse_args()

    if args.command == "write-result":
        result = json.load(sys.stdin)
        output = write_result(args.session, args.mode, result)
        print(json.dumps(output))

    elif args.command == "session-status":
        output = get_session_status(args.session)
        print(json.dumps(output, indent=2))

    elif args.command == "aggregate-session":
        exploration = aggregate_session(args.session, args.objective)
        print(json.dumps(exploration, indent=2))

    elif args.command == "clear-session":
        output = clear_session(args.session)
        print(json.dumps(output))

    elif args.command == "aggregate":
        results = []
        for line in sys.stdin:
            line = line.strip()
            if line:
                parsed = extract_json(line)
                if parsed is not None:
                    results.append(parsed)
        exploration = aggregate(results, args.objective)
        print(json.dumps(exploration, indent=2))

    elif args.command == "write":
        exploration = json.load(sys.stdin)
        result = write(exploration)
        print(json.dumps(result))

    elif args.command == "read":
        campaign_id = getattr(args, 'campaign_id', None)
        exploration = read(campaign_id=campaign_id)
        if exploration:
            print(json.dumps(exploration, indent=2))
        else:
            print("null")

    elif args.command == "get-structure":
        print(json.dumps(get_structure(), indent=2))

    elif args.command == "get-pattern":
        print(json.dumps(get_pattern(), indent=2))

    elif args.command == "get-memory":
        print(json.dumps(get_memory(), indent=2))

    elif args.command == "get-delta":
        print(json.dumps(get_delta(), indent=2))

    elif args.command == "clear":
        result = clear()
        print(json.dumps(result))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
