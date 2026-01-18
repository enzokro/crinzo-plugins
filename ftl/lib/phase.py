#!/usr/bin/env python3
"""Phase state tracking with fastsql database backend.

Tracks phase transitions and validates workflow order.
"""

from pathlib import Path
from datetime import datetime
import json
import argparse
import sys

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, PhaseState
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db, PhaseState


# Note: All storage is now in .ftl/ftl.db

# Valid phases in workflow order
PHASES = ["none", "explore", "plan", "build", "observe", "complete"]

# Valid transitions (from -> [valid destinations])
VALID_TRANSITIONS = {
    "none": ["explore"],
    "explore": ["plan"],
    "plan": ["build", "explore"],  # Can go back to explore if CLARIFY
    "build": ["observe", "build"],  # Can stay in build for multi-task
    "observe": ["complete"],
    "complete": ["none"],  # Reset for next campaign
}


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def _get_phase_state():
    """Get or create the phase state singleton."""
    db = _ensure_db()
    phase_states = db.t.phase_state

    rows = list(phase_states.rows)
    if rows:
        return rows[0]

    # Create initial state
    state = PhaseState(
        phase="none",
        started_at=None,
        transitions="[]"
    )
    phase_states.insert(state)
    return list(phase_states.rows)[0]


def get_state() -> dict:
    """Get current phase state.

    Returns:
        {"phase": str, "started_at": str, "transitions": []}
    """
    row = _get_phase_state()
    return {
        "phase": row.get("phase", "none"),
        "started_at": row.get("started_at"),
        "transitions": json.loads(row.get("transitions") or "[]")
    }


def can_transition(from_phase: str, to_phase: str) -> bool:
    """Check if a phase transition is valid.

    Args:
        from_phase: Current phase
        to_phase: Target phase

    Returns:
        True if transition is valid
    """
    valid_destinations = VALID_TRANSITIONS.get(from_phase, [])
    return to_phase in valid_destinations


def transition(to_phase: str) -> dict:
    """Transition to a new phase.

    Args:
        to_phase: Target phase

    Returns:
        Updated state dict

    Raises:
        ValueError: If transition is invalid
    """
    db = _ensure_db()
    phase_states = db.t.phase_state

    state = get_state()
    current_phase = state["phase"]

    if not can_transition(current_phase, to_phase):
        raise ValueError(
            f"Invalid transition: {current_phase} -> {to_phase}. "
            f"Valid destinations: {VALID_TRANSITIONS.get(current_phase, [])}"
        )

    now = datetime.now().isoformat()

    # Record transition
    transitions = state["transitions"]
    transitions.append({
        "from": current_phase,
        "to": to_phase,
        "at": now
    })

    # Update state
    started_at = state["started_at"]
    if current_phase == "none":
        started_at = now

    # Get the row and update
    row = _get_phase_state()
    phase_states.update({
        "phase": to_phase,
        "started_at": started_at,
        "transitions": json.dumps(transitions)
    }, row["id"])

    return {
        "phase": to_phase,
        "started_at": started_at,
        "transitions": transitions
    }


def reset() -> dict:
    """Reset phase state to 'none'.

    Returns:
        New empty state dict
    """
    db = _ensure_db()
    phase_states = db.t.phase_state

    # Delete all existing states
    for row in list(phase_states.rows):
        phase_states.delete(row["id"])

    return {
        "phase": "none",
        "started_at": None,
        "transitions": []
    }


def get_duration() -> float | None:
    """Get duration of current workflow in seconds.

    Returns:
        Duration in seconds or None if no workflow started
    """
    state = get_state()
    if not state.get("started_at"):
        return None

    try:
        started = datetime.fromisoformat(state["started_at"])
        return (datetime.now() - started).total_seconds()
    except (ValueError, TypeError):
        return None


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL phase state tracking")
    subparsers = parser.add_subparsers(dest="command")

    # status command
    subparsers.add_parser("status", help="Get current phase state")

    # transition command
    t = subparsers.add_parser("transition", help="Transition to new phase")
    t.add_argument("phase", choices=PHASES, help="Target phase")

    # reset command
    subparsers.add_parser("reset", help="Reset phase state")

    # can-transition command
    ct = subparsers.add_parser("can-transition", help="Check if transition is valid")
    ct.add_argument("from_phase", choices=PHASES, help="Current phase")
    ct.add_argument("to_phase", choices=PHASES, help="Target phase")

    # duration command
    subparsers.add_parser("duration", help="Get workflow duration")

    args = parser.parse_args()

    if args.command == "status":
        state = get_state()
        print(json.dumps(state, indent=2))

    elif args.command == "transition":
        try:
            state = transition(args.phase)
            print(json.dumps(state, indent=2))
        except ValueError as e:
            print(f"Error: {e}")
            sys.exit(1)

    elif args.command == "reset":
        state = reset()
        print(json.dumps(state, indent=2))

    elif args.command == "can-transition":
        result = can_transition(args.from_phase, args.to_phase)
        print("valid" if result else "invalid")

    elif args.command == "duration":
        duration = get_duration()
        if duration is not None:
            print(f"{duration:.2f} seconds")
        else:
            print("No workflow started")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
