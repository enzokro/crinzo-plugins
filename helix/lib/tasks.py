#!/usr/bin/env python3
"""Task state helper for helix orchestrator.

This module provides:
- helix_task_state(): Derive canonical task state from dual status model

Note: The actual TaskCreate/TaskList/TaskGet/TaskUpdate calls are made
directly by the orchestrator using Claude Code's native Task tools.

ARCHITECTURAL PRINCIPLE: Single Source of Truth
-----------------------------------------------
Task state is tracked in TaskList metadata via 'helix_outcome' field.
Builder writes outcome via TaskUpdate; orchestrator reads via TaskGet.
Never use TaskOutput for builders - wastes context loading full transcript.
"""

import json


def helix_task_state(task: dict) -> dict:
    """Derive canonical helix task state from task data.

    Interprets the dual status model:
    - Native `status`: Controls DAG execution (pending/in_progress/completed)
    - Helix `helix_outcome`: Captures semantic result (delivered/blocked/skipped)

    Args:
        task: Task data from TaskList/TaskGet

    Returns:
        {
            "executable": True if task can be executed (pending, unblocked),
            "finished": True if task is done (status=completed),
            "successful": True if finished AND helix_outcome=delivered,
            "outcome": "delivered"|"blocked"|"skipped"|"pending"|"in_progress",
            "blocks_dependents": True if this task failing blocks others
        }
    """
    status = task.get("status", "pending")
    helix_outcome = task.get("metadata", {}).get("helix_outcome")
    blocked_by = task.get("blockedBy", [])

    finished = status == "completed"
    executable = status == "pending" and len(blocked_by) == 0

    # Determine canonical outcome
    if finished:
        outcome = helix_outcome or "delivered"  # Default to delivered if not set
    else:
        outcome = status  # "pending" or "in_progress"

    successful = finished and outcome == "delivered"
    blocks_dependents = finished and outcome in ("blocked", "skipped")

    return {
        "executable": executable,
        "finished": finished,
        "successful": successful,
        "outcome": outcome,
        "blocks_dependents": blocks_dependents
    }


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix task state helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # task-state
    p = subparsers.add_parser("task-state", help="Derive canonical task state")
    p.add_argument("task_json", help="Task JSON from TaskGet")

    args = parser.parse_args()

    if args.command == "task-state":
        task = json.loads(args.task_json)
        result = helix_task_state(task)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
