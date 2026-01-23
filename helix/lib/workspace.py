#!/usr/bin/env python3
"""Workspace module - execution context for tasks.

A workspace contains everything the builder needs:
- Task details (objective, delta, verify)
- Memory context (failures to avoid, patterns to apply)
- Lineage (what previous tasks delivered)

Memory is now integrated directly (no subprocess calls).
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .db.connection import get_db, write_lock
    from .memory import recall, feedback
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock
    from memory import recall, feedback


def _query_memory(objective: str, limit: int = 5) -> List[dict]:
    """Query memory system for relevant memories.

    Direct call to memory layer - no subprocess overhead.
    """
    try:
        return recall(objective, limit=limit)
    except Exception:
        return []


def _send_feedback(utilized: List[str], injected: List[str]) -> dict:
    """Send feedback to memory system - CLOSES THE LOOP.

    Direct call to memory layer - guaranteed execution.

    Args:
        utilized: Memory names that actually helped (honest reporting!)
        injected: Memory names that were injected

    Returns:
        Result dict with helped/unhelpful counts
    """
    try:
        return feedback(utilized, injected)
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def create(
    plan_id: int,
    task: dict,
    framework: Optional[str] = None,
    idioms: Optional[dict] = None,
    memories: Optional[List[dict]] = None,
) -> dict:
    """Create a workspace for a task.

    Automatically injects:
    - Relevant failures (semantic similarity to objective)
    - Relevant patterns (semantic similarity to objective)
    - Lineage from parent tasks
    """
    db = get_db()
    now = datetime.now().isoformat()

    task_seq = task["seq"]
    task_slug = task.get("slug", f"task-{task_seq}")
    objective = task.get("objective", "")

    # Query memory if not provided
    if memories is None:
        memories = _query_memory(objective, limit=8)

    # Separate by type
    failures = [m for m in memories if m.get("type") == "failure"]
    patterns = [m for m in memories if m.get("type") == "pattern"]

    # Build lineage from parent tasks
    lineage = _build_lineage(plan_id, task.get("depends", "none"))

    # Build workspace data
    data = {
        "task_seq": task_seq,
        "task_slug": task_slug,
        "objective": objective,
        "delta": task.get("delta", []),
        "verify": task.get("verify", ""),
        "budget": task.get("budget", 7),
        "framework": framework,
        "idioms": idioms or {},
        "failures": failures,
        "patterns": patterns,
        "lineage": lineage,
    }

    with write_lock():
        cursor = db.execute(
            """INSERT INTO workspace (plan_id, task_seq, task_slug, objective, data, status, created_at)
               VALUES (?, ?, ?, ?, ?, 'active', ?)""",
            (plan_id, task_seq, task_slug, objective, json.dumps(data), now)
        )
        db.commit()

        data["_id"] = cursor.lastrowid
        data["_injected"] = [f["name"] for f in failures] + [p["name"] for p in patterns]
        return data


def load(workspace_id: Optional[int] = None, task_seq: Optional[str] = None) -> Optional[dict]:
    """Load a workspace by id or task_seq."""
    db = get_db()

    if workspace_id:
        row = db.execute("SELECT * FROM workspace WHERE id = ?", (workspace_id,)).fetchone()
    elif task_seq:
        row = db.execute(
            "SELECT * FROM workspace WHERE task_seq = ? ORDER BY id DESC LIMIT 1",
            (task_seq,)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM workspace WHERE status = 'active' ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    data = json.loads(row["data"])
    data["_id"] = row["id"]
    data["_plan_id"] = row["plan_id"]
    data["_status"] = row["status"]
    data["_delivered"] = row["delivered"]
    data["_utilized"] = json.loads(row["utilized"]) if row["utilized"] else []
    data["_created_at"] = row["created_at"]
    return data


def complete(workspace_id: int, delivered: str, utilized: List[str]) -> dict:
    """Mark workspace as complete.

    Args:
        workspace_id: Workspace to complete
        delivered: Summary of what was delivered
        utilized: List of memory names that actually helped (HONEST REPORTING!)
    """
    db = get_db()
    feedback_result = None

    with write_lock():
        # Update workspace
        db.execute(
            "UPDATE workspace SET status = 'complete', delivered = ?, utilized = ? WHERE id = ?",
            (delivered, json.dumps(utilized), workspace_id)
        )

        # Get workspace data for feedback
        row = db.execute("SELECT * FROM workspace WHERE id = ?", (workspace_id,)).fetchone()
        if row:
            data = json.loads(row["data"])
            injected = [f["name"] for f in data.get("failures", [])] + \
                       [p["name"] for p in data.get("patterns", [])]

            # CLOSE THE LOOP - direct call, guaranteed execution!
            feedback_result = _send_feedback(utilized, injected)

            # Update plan task
            if row["plan_id"]:
                from . import plan as plan_module
                plan_module.update_task(
                    row["plan_id"],
                    row["task_seq"],
                    {"status": "complete", "delivered": delivered, "utilized_memories": utilized}
                )

        db.commit()

    return {
        "status": "complete",
        "workspace_id": workspace_id,
        "utilized": utilized,
        "feedback": feedback_result
    }


def block(workspace_id: int, reason: str, utilized: List[str] = None) -> dict:
    """Mark workspace as blocked.

    Args:
        workspace_id: Workspace to block
        reason: Why it was blocked
        utilized: List of memory names that were still helpful
    """
    utilized = utilized or []
    db = get_db()
    feedback_result = None

    with write_lock():
        db.execute(
            "UPDATE workspace SET status = 'blocked', delivered = ?, utilized = ? WHERE id = ?",
            (f"BLOCKED: {reason}", json.dumps(utilized), workspace_id)
        )

        # Get workspace data for feedback
        row = db.execute("SELECT * FROM workspace WHERE id = ?", (workspace_id,)).fetchone()
        if row:
            data = json.loads(row["data"])
            injected = [f["name"] for f in data.get("failures", [])] + \
                       [p["name"] for p in data.get("patterns", [])]

            # Feedback even on block - we learn what didn't help
            feedback_result = _send_feedback(utilized, injected)

            # Update plan task
            if row["plan_id"]:
                from . import plan as plan_module
                plan_module.update_task(
                    row["plan_id"],
                    row["task_seq"],
                    {"status": "blocked", "blocked_reason": reason, "utilized_memories": utilized}
                )

        db.commit()

    return {
        "status": "blocked",
        "workspace_id": workspace_id,
        "reason": reason,
        "feedback": feedback_result
    }


def list_workspaces(status: Optional[str] = None, plan_id: Optional[int] = None) -> List[dict]:
    """List workspaces with optional filtering."""
    db = get_db()

    sql = "SELECT id, plan_id, task_seq, task_slug, objective, status, delivered, created_at FROM workspace"
    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)
    if plan_id:
        conditions.append("plan_id = ?")
        params.append(plan_id)

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY id DESC"

    rows = db.execute(sql, params).fetchall()

    return [{
        "id": r["id"],
        "plan_id": r["plan_id"],
        "task_seq": r["task_seq"],
        "task_slug": r["task_slug"],
        "objective": r["objective"],
        "status": r["status"],
        "delivered": r["delivered"],
        "created_at": r["created_at"],
    } for r in rows]


def _build_lineage(plan_id: int, depends: str) -> dict:
    """Build lineage from parent task deliveries."""
    if depends == "none" or not depends:
        return {}

    deps = [d.strip() for d in str(depends).split(",") if d.strip() and d.strip() != "none"]
    if not deps:
        return {}

    db = get_db()
    lineage = {"parents": []}

    for dep_seq in deps:
        row = db.execute(
            """SELECT task_seq, task_slug, delivered FROM workspace
               WHERE plan_id = ? AND task_seq = ? AND status = 'complete'
               ORDER BY id DESC LIMIT 1""",
            (plan_id, dep_seq)
        ).fetchone()

        if row:
            lineage["parents"].append({
                "seq": row["task_seq"],
                "slug": row["task_slug"],
                "delivered": row["delivered"],
            })

    return lineage


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix workspace operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    p = subparsers.add_parser("create")
    p.add_argument("--plan-id", type=int, required=True)
    p.add_argument("--task", required=True, help="JSON task dict")
    p.add_argument("--framework", default=None)
    p.add_argument("--idioms", default=None, help="JSON idioms dict")
    p.add_argument("--memories", default=None, help="JSON list of memories to inject")

    # load
    p = subparsers.add_parser("load")
    p.add_argument("--id", type=int, default=None)
    p.add_argument("--task-seq", default=None)

    # complete
    p = subparsers.add_parser("complete")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--delivered", required=True)
    p.add_argument("--utilized", required=True, help="JSON list of memory names")

    # block
    p = subparsers.add_parser("block")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--reason", required=True)
    p.add_argument("--utilized", default="[]", help="JSON list of memory names")

    # list
    p = subparsers.add_parser("list")
    p.add_argument("--status", default=None)
    p.add_argument("--plan-id", type=int, default=None)

    args = parser.parse_args()

    if args.command == "create":
        idioms = json.loads(args.idioms) if args.idioms else None
        memories = json.loads(args.memories) if args.memories else None
        result = create(args.plan_id, json.loads(args.task), args.framework, idioms, memories)
    elif args.command == "load":
        result = load(args.id, args.task_seq)
        if result is None:
            result = {"error": "Workspace not found"}
    elif args.command == "complete":
        result = complete(args.id, args.delivered, json.loads(args.utilized))
    elif args.command == "block":
        result = block(args.id, args.reason, json.loads(args.utilized))
    elif args.command == "list":
        result = list_workspaces(args.status, args.plan_id)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
