#!/usr/bin/env python3
"""DAG utilities for SKILL.md orchestration.

SKILL.md is the orchestrator. This module provides mechanical operations:
- detect_cycles(): Find dependency loops
- get_ready_tasks(): Identify unblocked tasks
- check_stalled(): Detect build impasse

Code surfaces facts. SKILL.md decides actions.

ARCHITECTURAL PRINCIPLE: Single Source of Truth
-----------------------------------------------
Task state is derived FROM TaskList metadata (helix_outcome field),
not maintained in parallel. The orchestrator is prose-driven (SKILL.md),
not code-driven - these are utilities, not a state machine.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def detect_cycles(dependencies: Dict[str, List[str]]) -> List[List[str]]:
    """Detect cycles in dependency graph using DFS.

    Args:
        dependencies: Dict mapping task_id -> list of blocker task_ids

    Returns:
        List of cycles found (each cycle is a list of task_ids)
    """
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: List[str]) -> None:
        if node in rec_stack:
            try:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
            except ValueError:
                pass
            return

        if node in visited:
            return

        visited.add(node)
        rec_stack.add(node)

        for neighbor in dependencies.get(node, []):
            dfs(neighbor, path + [node])

        rec_stack.discard(node)

    for node in dependencies:
        if node not in visited:
            dfs(node, [])

    return cycles


def get_completed_task_ids(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that completed successfully (delivered).

    Derives state from TaskList metadata, not from parallel tracking.

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        List of task IDs with helix_outcome == "delivered"
    """
    return [
        t.get("id") for t in all_tasks
        if t.get("status") == "completed"
        and t.get("metadata", {}).get("helix_outcome") == "delivered"
    ]


def get_blocked_task_ids(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that were blocked.

    Derives state from TaskList metadata, not from parallel tracking.

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        List of task IDs with helix_outcome == "blocked"
    """
    return [
        t.get("id") for t in all_tasks
        if t.get("status") == "completed"
        and t.get("metadata", {}).get("helix_outcome") == "blocked"
    ]


def get_ready_tasks(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that are ready to execute.

    A task is ready if:
    - status == "pending"
    - all blockedBy tasks are completed with helix_outcome == "delivered"

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        List of task IDs ready for execution
    """
    ready = []

    # Build set of successfully completed task IDs
    completed_ids = set(get_completed_task_ids(all_tasks))
    blocked_ids = set(get_blocked_task_ids(all_tasks))

    for task in all_tasks:
        if task.get("status") != "pending":
            continue

        blockers = task.get("blockedBy", [])
        # All blockers must be completed AND not blocked
        all_blockers_done = all(
            b in completed_ids and b not in blocked_ids
            for b in blockers
        )

        if all_blockers_done:
            ready.append(task.get("id"))

    return ready


def check_stalled(all_tasks: List[Dict]) -> Tuple[bool, Optional[Dict]]:
    """Check if build is stalled.

    Stalled = pending tasks exist but none are ready
    (all are blocked by BLOCKED tasks)

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        (is_stalled, stall_info)
    """
    pending = [t for t in all_tasks if t.get("status") == "pending"]
    if not pending:
        return False, None

    ready = get_ready_tasks(all_tasks)
    if ready:
        return False, None

    # Stalled - analyze why
    blocked_ids = set(get_blocked_task_ids(all_tasks))
    blocked_by_blocked = []

    for task in pending:
        blockers = task.get("blockedBy", [])
        blocked_blockers = [b for b in blockers if b in blocked_ids]
        if blocked_blockers:
            blocked_by_blocked.append({
                "task_id": task.get("id"),
                "subject": task.get("subject"),
                "blocked_by": blocked_blockers
            })

    return True, {
        "pending_count": len(pending),
        "blocked_by_blocked": blocked_by_blocked
    }


def clear_checkpoints() -> int:
    """Clear all checkpoints (for starting fresh).

    Returns:
        Number of checkpoints cleared
    """
    cp_dir = Path.cwd() / ".helix" / "checkpoints"
    if not cp_dir.exists():
        return 0

    count = 0
    for cp_file in cp_dir.glob("*.json"):
        cp_file.unlink()
        count += 1

    return count


# CLI for utilities
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Helix DAG utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # clear command
    subparsers.add_parser("clear", help="Clear all checkpoints")

    # detect-cycles command
    p = subparsers.add_parser("detect-cycles", help="Check for cycles in dependencies")
    p.add_argument("--dependencies", required=True, help="JSON dict of task_id -> blocker_ids")

    # check-stalled command
    p = subparsers.add_parser("check-stalled", help="Check if build is stalled")
    p.add_argument("--tasks", required=True, help="JSON list of task data from TaskList")

    args = parser.parse_args()

    if args.cmd == "clear":
        count = clear_checkpoints()
        print(json.dumps({"cleared": count}))

    elif args.cmd == "detect-cycles":
        deps = json.loads(args.dependencies)
        cycles = detect_cycles(deps)
        print(json.dumps({"cycles": cycles, "has_cycles": len(cycles) > 0}))

    elif args.cmd == "check-stalled":
        tasks = json.loads(args.tasks)
        is_stalled, info = check_stalled(tasks)
        print(json.dumps({"stalled": is_stalled, "info": info}))
