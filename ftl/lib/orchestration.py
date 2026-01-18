#!/usr/bin/env python3
"""Orchestration utilities for FTL workflow management.

Provides:
- Quorum-based waiting for explorer completion with timeout
- Phase transition validation
- Agent coordination helpers
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path


CACHE_DIR = Path(".ftl/cache")
EXPLORER_MODES = ["structure", "pattern", "memory", "delta"]
DEFAULT_TIMEOUT = 300  # 5 minutes
DEFAULT_QUORUM = 3     # 3 of 4 explorers sufficient


def wait_explorers(
    required: int = DEFAULT_QUORUM,
    timeout: int = DEFAULT_TIMEOUT,
    poll_interval: float = 2.0
) -> dict:
    """Wait for explorer agents to complete with quorum support.

    Args:
        required: Minimum number of explorers that must complete (default: 3)
        timeout: Maximum seconds to wait (default: 300)
        poll_interval: Seconds between checks (default: 2.0)

    Returns:
        {
            "status": "quorum_met" | "timeout" | "all_complete",
            "completed": ["structure", "pattern", ...],
            "missing": ["delta"],
            "elapsed": 45.2,
            "exploration_files": {"structure": "path/to/file", ...}
        }
    """
    start = time.time()
    completed = []
    exploration_files = {}

    while True:
        elapsed = time.time() - start

        # Check each explorer's cache file
        for mode in EXPLORER_MODES:
            if mode in completed:
                continue

            cache_file = CACHE_DIR / f"explorer_{mode}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    if data.get("status") in ["ok", "partial", "error"]:
                        completed.append(mode)
                        exploration_files[mode] = str(cache_file)
                except (json.JSONDecodeError, IOError):
                    pass

        # Check completion conditions
        missing = [m for m in EXPLORER_MODES if m not in completed]

        if len(completed) >= len(EXPLORER_MODES):
            return {
                "status": "all_complete",
                "completed": completed,
                "missing": [],
                "elapsed": round(elapsed, 2),
                "exploration_files": exploration_files,
            }

        if len(completed) >= required:
            return {
                "status": "quorum_met",
                "completed": completed,
                "missing": missing,
                "elapsed": round(elapsed, 2),
                "exploration_files": exploration_files,
            }

        if elapsed >= timeout:
            return {
                "status": "timeout",
                "completed": completed,
                "missing": missing,
                "elapsed": round(elapsed, 2),
                "exploration_files": exploration_files,
            }

        time.sleep(poll_interval)


def check_explorers() -> dict:
    """Non-blocking check of explorer status.

    Returns:
        {
            "total": 4,
            "completed": 2,
            "modes": {"structure": "ok", "pattern": "ok", "memory": "pending", "delta": "pending"}
        }
    """
    modes = {}
    completed = 0

    for mode in EXPLORER_MODES:
        cache_file = CACHE_DIR / f"explorer_{mode}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text())
                status = data.get("status", "unknown")
                modes[mode] = status
                if status in ["ok", "partial", "error"]:
                    completed += 1
            except (json.JSONDecodeError, IOError):
                modes[mode] = "error"
        else:
            modes[mode] = "pending"

    return {
        "total": len(EXPLORER_MODES),
        "completed": completed,
        "modes": modes,
    }


def validate_transition(from_state: str, to_state: str) -> dict:
    """Validate a state machine transition.

    This validates TASK flow transitions only. CAMPAIGN flow uses additional
    internal states (REGISTER, EXECUTE, CASCADE) that are orchestrated by
    SKILL.md state machine logic, not validated here. Those states are
    CAMPAIGN-internal: they follow PLAN→REGISTER→EXECUTE→CASCADE→OBSERVE
    but validation happens at the SKILL.md orchestration layer.

    Args:
        from_state: Current state
        to_state: Target state

    Returns:
        {"valid": bool, "reason": str}
    """
    # TASK flow transitions. CAMPAIGN states (REGISTER, EXECUTE, CASCADE)
    # are orchestrated by SKILL.md and bypass this validation.
    valid_transitions = {
        "INIT": ["EXPLORE"],
        "EXPLORE": ["PLAN"],
        "PLAN": ["BUILD", "EXPLORE"],  # EXPLORE if CLARIFY
        "BUILD": ["OBSERVE", "BUILD"],  # BUILD for multi-task
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
    event = {
        "event": "STATE_ENTRY",
        "state": state,
        "timestamp": datetime.now().isoformat(),
        **kwargs
    }

    # Write to event log
    log_file = Path(".ftl/events.jsonl")
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with log_file.open("a") as f:
        f.write(json.dumps(event) + "\n")

    return event


def main():
    parser = argparse.ArgumentParser(description="FTL orchestration utilities")
    subparsers = parser.add_subparsers(dest="command")

    # wait-explorers command
    we = subparsers.add_parser("wait-explorers", help="Wait for explorers with quorum")
    we.add_argument("--required", type=int, default=DEFAULT_QUORUM,
                    help=f"Minimum explorers required (default: {DEFAULT_QUORUM})")
    we.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                    help=f"Timeout in seconds (default: {DEFAULT_TIMEOUT})")

    # check-explorers command
    subparsers.add_parser("check-explorers", help="Non-blocking explorer status check")

    # validate-transition command
    vt = subparsers.add_parser("validate-transition", help="Validate state transition")
    vt.add_argument("from_state", help="Current state")
    vt.add_argument("to_state", help="Target state")

    # emit-state command
    es = subparsers.add_parser("emit-state", help="Emit state entry event")
    es.add_argument("state", help="State name")
    es.add_argument("--meta", help="JSON metadata string")

    args = parser.parse_args()

    if args.command == "wait-explorers":
        result = wait_explorers(args.required, args.timeout)
        print(json.dumps(result, indent=2))
        # Exit with error code if timeout
        sys.exit(0 if result["status"] != "timeout" else 1)

    elif args.command == "check-explorers":
        result = check_explorers()
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
