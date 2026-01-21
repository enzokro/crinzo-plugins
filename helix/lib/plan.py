#!/usr/bin/env python3
"""Plan module - task decomposition with DAG dependencies.

The planner produces a Plan, the orchestrator executes it.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .db.connection import get_db, write_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock


def save(plan: dict) -> dict:
    """Save a plan.

    Args:
        plan: Dict with keys:
            - objective: str
            - framework: str | None
            - idioms: dict
            - tasks: list of task dicts

    Returns:
        {"id": int, "task_count": int}
    """
    db = get_db()
    now = datetime.now().isoformat()

    # Validate tasks have required fields
    tasks = plan.get("tasks", [])
    for i, task in enumerate(tasks):
        if "seq" not in task:
            task["seq"] = f"{i+1:03d}"
        if "slug" not in task:
            task["slug"] = f"task-{i+1}"
        if "status" not in task:
            task["status"] = "pending"

    # Check for cycles
    cycle = _detect_cycle(tasks)
    if cycle:
        return {"error": f"Cycle detected: {' -> '.join(cycle)}"}

    with write_lock():
        cursor = db.execute(
            """INSERT INTO plan (objective, framework, idioms, tasks, status, created_at)
               VALUES (?, ?, ?, ?, 'active', ?)""",
            (
                plan.get("objective", ""),
                plan.get("framework"),
                json.dumps(plan.get("idioms", {})),
                json.dumps(tasks),
                now
            )
        )
        db.commit()
        return {"id": cursor.lastrowid, "task_count": len(tasks)}


def load(plan_id: Optional[int] = None) -> Optional[dict]:
    """Load a plan. If no id, returns active plan."""
    db = get_db()

    if plan_id:
        row = db.execute("SELECT * FROM plan WHERE id = ?", (plan_id,)).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM plan WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    return {
        "id": row["id"],
        "objective": row["objective"],
        "framework": row["framework"],
        "idioms": json.loads(row["idioms"]) if row["idioms"] else {},
        "tasks": json.loads(row["tasks"]),
        "status": row["status"],
        "created_at": row["created_at"],
    }


def update_task(plan_id: int, task_seq: str, updates: dict) -> dict:
    """Update a task within a plan.

    updates can include: status, delivered, blocked_reason, utilized_memories
    """
    db = get_db()

    with write_lock():
        row = db.execute("SELECT tasks FROM plan WHERE id = ?", (plan_id,)).fetchone()
        if not row:
            return {"error": f"Plan not found: {plan_id}"}

        tasks = json.loads(row["tasks"])
        found = False

        for task in tasks:
            if task["seq"] == task_seq:
                task.update(updates)
                found = True
                break

        if not found:
            return {"error": f"Task not found: {task_seq}"}

        db.execute("UPDATE plan SET tasks = ? WHERE id = ?", (json.dumps(tasks), plan_id))
        db.commit()

        return {"status": "updated", "task_seq": task_seq}


def ready_tasks(plan_id: Optional[int] = None) -> List[dict]:
    """Get tasks whose dependencies are all complete."""
    plan = load(plan_id)
    if not plan:
        return []

    tasks = plan["tasks"]
    complete_seqs = {t["seq"] for t in tasks if t.get("status") == "complete"}

    ready = []
    for task in tasks:
        if task.get("status") != "pending":
            continue

        depends = task.get("depends", "none")
        if depends == "none" or not depends:
            ready.append(task)
            continue

        deps = [d.strip() for d in str(depends).split(",") if d.strip() and d.strip() != "none"]
        if all(d in complete_seqs for d in deps):
            ready.append(task)

    return ready


def cascade_status(plan_id: Optional[int] = None) -> dict:
    """Check if plan is stuck due to blocked dependencies."""
    plan = load(plan_id)
    if not plan:
        return {"state": "none"}

    tasks = plan["tasks"]
    if not tasks:
        return {"state": "complete", "ready": 0, "complete": 0, "blocked": 0, "pending": 0}

    # Count by status
    counts = {
        "complete": sum(1 for t in tasks if t.get("status") == "complete"),
        "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
        "active": sum(1 for t in tasks if t.get("status") == "active"),
    }

    ready = ready_tasks(plan_id)
    counts["ready"] = len(ready)

    if ready:
        return {"state": "in_progress", **counts}

    if counts["pending"] == 0:
        return {"state": "complete", **counts}

    # Check for stuck: pending tasks with blocked deps
    blocked_seqs = {t["seq"] for t in tasks if t.get("status") == "blocked"}
    unreachable = []

    for task in tasks:
        if task.get("status") != "pending":
            continue

        depends = task.get("depends", "none")
        if depends == "none" or not depends:
            continue

        deps = [d.strip() for d in str(depends).split(",") if d.strip() and d.strip() != "none"]
        blocking = [d for d in deps if d in blocked_seqs]

        if blocking:
            unreachable.append({"seq": task["seq"], "blocked_by": blocking})

    if unreachable:
        return {"state": "stuck", **counts, "unreachable": unreachable}

    return {"state": "all_blocked", **counts}


def complete(plan_id: int) -> dict:
    """Mark plan as complete."""
    db = get_db()
    with write_lock():
        db.execute("UPDATE plan SET status = 'complete' WHERE id = ?", (plan_id,))
        db.commit()
    return {"status": "complete", "plan_id": plan_id}


def _detect_cycle(tasks: List[dict]) -> Optional[List[str]]:
    """Detect cycles in task dependencies using DFS."""
    task_seqs = {t["seq"] for t in tasks}

    def get_deps(task):
        depends = task.get("depends", "none")
        if depends == "none" or not depends:
            return []
        return [d.strip() for d in str(depends).split(",") if d.strip() and d.strip() != "none"]

    deps_map = {t["seq"]: get_deps(t) for t in tasks}

    visited = set()
    path = []
    path_set = set()

    def dfs(seq):
        if seq in path_set:
            cycle_start = path.index(seq)
            return path[cycle_start:] + [seq]

        if seq in visited:
            return None

        path.append(seq)
        path_set.add(seq)

        for dep in deps_map.get(seq, []):
            if dep in task_seqs:
                result = dfs(dep)
                if result:
                    return result

        path.pop()
        path_set.remove(seq)
        visited.add(seq)
        return None

    for seq in task_seqs:
        if seq not in visited:
            result = dfs(seq)
            if result:
                return result

    return None


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix plan operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # save
    subparsers.add_parser("save", help="Save plan (reads JSON from stdin)")

    # load
    p = subparsers.add_parser("load")
    p.add_argument("--id", type=int, default=None)

    # update-task
    p = subparsers.add_parser("update-task")
    p.add_argument("--plan-id", type=int, required=True)
    p.add_argument("--task-seq", required=True)
    p.add_argument("--updates", required=True, help="JSON dict of updates")

    # ready-tasks
    p = subparsers.add_parser("ready-tasks")
    p.add_argument("--plan-id", type=int, default=None)

    # cascade-status
    p = subparsers.add_parser("cascade-status")
    p.add_argument("--plan-id", type=int, default=None)

    # complete
    p = subparsers.add_parser("complete")
    p.add_argument("--plan-id", type=int, required=True)

    args = parser.parse_args()

    if args.command == "save":
        data = json.load(sys.stdin)
        result = save(data)
    elif args.command == "load":
        result = load(args.id)
        if result is None:
            result = {"error": "No plan found"}
    elif args.command == "update-task":
        result = update_task(args.plan_id, args.task_seq, json.loads(args.updates))
    elif args.command == "ready-tasks":
        result = ready_tasks(args.plan_id)
    elif args.command == "cascade-status":
        result = cascade_status(args.plan_id)
    elif args.command == "complete":
        result = complete(args.plan_id)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
