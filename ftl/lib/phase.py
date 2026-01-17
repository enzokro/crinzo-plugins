#!/usr/bin/env python3
"""Phase state tracking for FTL workflow.

Tracks phase transitions in .ftl/phase_state.json and validates
that transitions follow the expected workflow order.
"""

from pathlib import Path
from datetime import datetime
import json

PHASE_STATE_FILE = Path(".ftl/phase_state.json")

# Valid phases in workflow order
PHASES = ["none", "explore", "plan", "build", "observe", "complete"]

# Valid transitions (from -> [valid destinations])
VALID_TRANSITIONS = {
    "none": ["explore"],
    "explore": ["plan"],
    "plan": ["build", "explore"],  # Can go back to explore if CLARIFY
    "build": ["observe", "build"],  # Can stay in build for multi-task campaigns
    "observe": ["complete"],
    "complete": ["none"],  # Reset for next campaign
}


def get_state() -> dict:
    """Get current phase state.

    Returns:
        {"phase": str, "started_at": str, "transitions": []}
    """
    if not PHASE_STATE_FILE.exists():
        return {
            "phase": "none",
            "started_at": None,
            "transitions": []
        }

    try:
        return json.loads(PHASE_STATE_FILE.read_text())
    except (json.JSONDecodeError, IOError):
        return {
            "phase": "none",
            "started_at": None,
            "transitions": []
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
    state = get_state()
    current_phase = state["phase"]

    if not can_transition(current_phase, to_phase):
        raise ValueError(
            f"Invalid transition: {current_phase} -> {to_phase}. "
            f"Valid destinations: {VALID_TRANSITIONS.get(current_phase, [])}"
        )

    now = datetime.now().isoformat()

    # Record transition
    state["transitions"].append({
        "from": current_phase,
        "to": to_phase,
        "at": now
    })

    # Update phase
    state["phase"] = to_phase
    if current_phase == "none":
        state["started_at"] = now

    # Write state
    PHASE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PHASE_STATE_FILE.write_text(json.dumps(state, indent=2))

    return state


def reset() -> dict:
    """Reset phase state to 'none'.

    Returns:
        New empty state dict
    """
    state = {
        "phase": "none",
        "started_at": None,
        "transitions": []
    }

    if PHASE_STATE_FILE.exists():
        PHASE_STATE_FILE.unlink()

    return state


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


if __name__ == "__main__":
    import argparse

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
            exit(1)

    elif args.command == "reset":
        state = reset()
        print(json.dumps(state, indent=2))

    elif args.command == "can-transition":
        result = can_transition(args.from_phase, args.to_phase)
        print("valid" if result else "invalid")

    else:
        parser.print_help()
