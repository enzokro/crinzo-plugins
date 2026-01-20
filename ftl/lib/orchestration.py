#!/usr/bin/env python3
"""Orchestration utilities with fastsql database backend.

Provides:
- Session-based exploration management
- Quorum-based waiting for explorer completion with timeout
- Phase transition validation
- Event logging
- Error state triggering for critical failures

CLI:
    python3 lib/orchestration.py create-session                    # Generate new session ID
    python3 lib/orchestration.py wait-explorers --session ID       # Wait for quorum
    python3 lib/orchestration.py check-explorers --session ID      # Non-blocking status
    python3 lib/orchestration.py validate-transition FROM TO       # Validate transition
    python3 lib/orchestration.py emit-state STATE                  # Emit state event
"""

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, Event
    from lib.exploration import get_session_status
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db, Event
    from exploration import get_session_status


# =============================================================================
# Configuration Constants (Hardcoded Defaults)
# =============================================================================
# These thresholds control orchestration behavior. Documented here per Pass 6.

EXPLORER_MODES = ["structure", "pattern", "memory", "delta"]  # The 4 parallel explorer agents
DEFAULT_TIMEOUT = 300     # 5 minutes - maximum wait time for explorer completion
DEFAULT_QUORUM = 3        # 3 of 4 explorers must complete (75% threshold)
SESSION_MAX_AGE_HOURS = 24  # Cleanup explorer results older than this


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def _cleanup_old_sessions(max_age_hours: int = SESSION_MAX_AGE_HOURS) -> int:
    """Remove explorer results from sessions older than max_age_hours.

    Args:
        max_age_hours: Maximum session age before cleanup

    Returns:
        Number of rows deleted
    """
    from datetime import timedelta
    try:
        from lib.exploration import clear_session
    except ImportError:
        from exploration import clear_session

    db = _ensure_db()
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    cutoff_str = cutoff.isoformat()

    # Find distinct old session IDs
    rows = list(db.t.explorer_result.rows)
    old_sessions = set()
    for row in rows:
        created = row.get("created_at", "")
        if created and created < cutoff_str:
            old_sessions.add(row.get("session_id"))

    # Clear each old session
    total_cleared = 0
    for session_id in old_sessions:
        if session_id:
            result = clear_session(session_id)
            total_cleared += result.get("cleared", 0)

    return total_cleared


def create_session() -> str:
    """Generate new exploration session ID.

    Performs opportunistic cleanup of sessions older than SESSION_MAX_AGE_HOURS
    to prevent indefinite accumulation of explorer results.

    Returns:
        8-character UUID string for session tracking
    """
    # Cleanup old sessions opportunistically
    try:
        _cleanup_old_sessions()
    except Exception as e:
        # Non-critical; log warning but don't fail session creation
        logging.warning(f"Session cleanup failed (non-critical): {e}")

    return str(uuid.uuid4())[:8]


def wait_explorers(
    session_id: str,
    required: int = DEFAULT_QUORUM,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: float = 2.0
) -> dict:
    """Wait for explorer agents to complete with quorum support.

    Uses database polling instead of file system polling.

    Args:
        session_id: UUID linking parallel explorers
        required: Minimum number of explorers that must complete
        timeout: Maximum seconds to wait
        poll_interval: Seconds between checks

    Returns:
        Status dict with completed and missing modes.
        Possible status values:
        - "all_complete": All 4 explorers finished
        - "quorum_met": Required number completed
        - "timeout": Time ran out but some explorers completed
        - "quorum_failure": Time ran out with zero completions (critical failure)
    """
    _ensure_db()
    start = time.time()

    while True:
        elapsed = time.time() - start
        status = get_session_status(session_id)

        if len(status["completed"]) >= len(EXPLORER_MODES):
            return {
                "status": "all_complete",
                "completed": status["completed"],
                "missing": [],
                "elapsed": round(elapsed, 2),
                "session_id": session_id
            }

        if len(status["completed"]) >= required:
            return {
                "status": "quorum_met",
                "completed": status["completed"],
                "missing": status["missing"],
                "elapsed": round(elapsed, 2),
                "session_id": session_id
            }

        if elapsed >= timeout:
            # Grace poll: one final check to catch late writes (WAL flush lag)
            time.sleep(0.5)
            status = get_session_status(session_id)
            # Distinguish timeout with partial results vs complete failure
            if len(status["completed"]) == 0:
                # Critical failure: no explorers completed at all
                return {
                    "status": "quorum_failure",
                    "completed": [],
                    "missing": status["missing"],
                    "elapsed": round(elapsed, 2),
                    "session_id": session_id
                }
            else:
                # Partial completion: some results available
                return {
                    "status": "timeout",
                    "completed": status["completed"],
                    "missing": status["missing"],
                    "elapsed": round(elapsed, 2),
                    "session_id": session_id
                }

        time.sleep(poll_interval)


def check_explorers(session_id: str) -> dict:
    """Non-blocking check of explorer status.

    Args:
        session_id: UUID linking parallel explorers

    Returns:
        Status dict with mode completion states
    """
    _ensure_db()
    status = get_session_status(session_id)

    modes = {}
    for mode in EXPLORER_MODES:
        if mode in status["completed"]:
            modes[mode] = "complete"
        else:
            modes[mode] = "pending"

    return {
        "total": len(EXPLORER_MODES),
        "completed": len(status["completed"]),
        "quorum_met": status["quorum_met"],
        "modes": modes,
        "session_id": session_id
    }


def validate_transition(from_state: str, to_state: str) -> dict:
    """Validate a state machine transition.

    Args:
        from_state: Current state
        to_state: Target state

    Returns:
        {"valid": bool, "reason": str}
    """
    valid_transitions = {
        "INIT": ["EXPLORE"],
        "EXPLORE": ["PLAN"],
        "PLAN": ["BUILD", "EXPLORE"],
        "BUILD": ["OBSERVE", "BUILD"],
        "OBSERVE": ["COMPLETE"],
        "COMPLETE": ["INIT"],
    }

    if from_state not in valid_transitions:
        return {"valid": False, "reason": f"Unknown state: {from_state}"}

    if to_state in valid_transitions[from_state]:
        return {"valid": True, "reason": ""}

    return {
        "valid": False,
        "reason": f"Invalid transition {from_state} -> {to_state}. Valid: {valid_transitions[from_state]}"
    }


def emit_state(state: str, **kwargs) -> dict:
    """Emit a state entry event with optional metadata.

    Args:
        state: State name
        **kwargs: Additional metadata

    Returns:
        Event dict
    """
    db = _ensure_db()
    events = db.t.event

    now = datetime.now().isoformat()
    metadata = {"state": state, **kwargs}

    event = Event(
        event_type="STATE_ENTRY",
        timestamp=now,
        metadata=json.dumps(metadata)
    )
    events.insert(event)

    return {
        "event": "STATE_ENTRY",
        "state": state,
        "timestamp": now,
        **kwargs
    }


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL orchestration utilities")
    subparsers = parser.add_subparsers(dest="command")

    # create-session command
    subparsers.add_parser("create-session", help="Generate new session ID")

    # wait-explorers command
    we = subparsers.add_parser("wait-explorers", help="Wait for explorers with quorum")
    we.add_argument("--session", required=True, help="Session ID")
    we.add_argument("--required", type=int, default=DEFAULT_QUORUM,
                    help=f"Minimum explorers required (default: {DEFAULT_QUORUM})")
    we.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})")

    # check-explorers command
    ce = subparsers.add_parser("check-explorers", help="Non-blocking explorer status check")
    ce.add_argument("--session", required=True, help="Session ID")

    # validate-transition command
    vt = subparsers.add_parser("validate-transition", help="Validate state transition")
    vt.add_argument("from_state", help="Current state")
    vt.add_argument("to_state", help="Target state")

    # emit-state command
    es = subparsers.add_parser("emit-state", help="Emit state entry event")
    es.add_argument("state", help="State name")
    es.add_argument("--meta", help="JSON metadata string")

    args = parser.parse_args()

    if args.command == "create-session":
        session_id = create_session()
        print(json.dumps({"session_id": session_id}))

    elif args.command == "wait-explorers":
        result = wait_explorers(args.session, args.required, args.timeout)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["status"] != "timeout" else 1)

    elif args.command == "check-explorers":
        result = check_explorers(args.session)
        print(json.dumps(result, indent=2))

    elif args.command == "validate-transition":
        result = validate_transition(args.from_state, args.to_state)
        print(json.dumps(result, indent=2))
        sys.exit(0 if result["valid"] else 1)

    elif args.command == "emit-state":
        meta = json.loads(args.meta) if args.meta else {}
        result = emit_state(args.state, **meta)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
