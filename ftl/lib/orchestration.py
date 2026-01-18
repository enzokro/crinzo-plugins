#!/usr/bin/env python3
"""Orchestration utilities with fastsql database backend.

Provides:
- Session-based exploration management
- Quorum-based waiting for explorer completion with timeout
- Phase transition validation
- Event logging

CLI:
    python3 lib/orchestration.py create-session                    # Generate new session ID
    python3 lib/orchestration.py wait-explorers --session ID       # Wait for quorum
    python3 lib/orchestration.py check-explorers --session ID      # Non-blocking status
    python3 lib/orchestration.py validate-transition FROM TO       # Validate transition
    python3 lib/orchestration.py emit-state STATE                  # Emit state event
"""

import argparse
import json
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


EXPLORER_MODES = ["structure", "pattern", "memory", "delta"]
DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_QUORUM = 3     # 3 of 4 explorers sufficient


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def create_session() -> str:
    """Generate new exploration session ID.

    Returns:
        8-character UUID string for session tracking
    """
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
        Status dict with completed and missing modes
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
