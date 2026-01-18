"""Plan storage and retrieval.

CLI:
    python3 lib/plan.py write < plan.json         # Store plan, print ID
    python3 lib/plan.py read --id ID              # Get plan by ID
    python3 lib/plan.py get-active                # Get most recent active plan
    python3 lib/plan.py mark-executed --id ID     # Mark plan as executed
    python3 lib/plan.py list [--status STATUS]    # List plans
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.db.connection import get_db, init_db
from lib.db.schema import Plan


def write(plan_dict: dict) -> int:
    """Store plan in database, return ID."""
    init_db()
    db = get_db()
    plan = Plan(
        campaign_id=plan_dict.get("campaign_id"),
        objective=plan_dict.get("objective", ""),
        framework=plan_dict.get("framework"),
        idioms=json.dumps(plan_dict.get("idioms", {})),
        tasks=json.dumps(plan_dict.get("tasks", [])),
        created_at=datetime.now().isoformat(),
        status="active"
    )
    result = db.t.plan.insert(plan)
    return result.id


def read(plan_id: int) -> dict | None:
    """Get plan by ID."""
    init_db()
    db = get_db()
    try:
        row = db.t.plan[plan_id]
        return {
            "id": row.id,
            "campaign_id": row.campaign_id,
            "objective": row.objective,
            "framework": row.framework,
            "idioms": json.loads(row.idioms),
            "tasks": json.loads(row.tasks),
            "status": row.status,
            "created_at": row.created_at
        }
    except (KeyError, IndexError):
        return None


def get_active() -> dict | None:
    """Get most recent active plan."""
    init_db()
    db = get_db()
    rows = list(db.t.plan.rows_where("status = ?", ["active"]))
    if not rows:
        return None
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return read(rows[0]["id"])


def mark_executed(plan_id: int) -> bool:
    """Mark plan as executed."""
    init_db()
    db = get_db()
    try:
        db.t.plan.update({"status": "executed"}, plan_id)
        return True
    except (KeyError, IndexError):
        return False


def mark_superseded(plan_id: int) -> bool:
    """Mark plan as superseded (replaced by newer plan)."""
    init_db()
    db = get_db()
    try:
        db.t.plan.update({"status": "superseded"}, plan_id)
        return True
    except (KeyError, IndexError):
        return False


def list_plans(status: str = None) -> list:
    """List plans, optionally filtered by status."""
    init_db()
    db = get_db()
    if status:
        rows = list(db.t.plan.rows_where("status = ?", [status]))
    else:
        rows = list(db.t.plan.rows)
    return [
        {
            "id": r["id"],
            "objective": r["objective"][:50] + "..." if len(r["objective"]) > 50 else r["objective"],
            "framework": r["framework"],
            "status": r["status"],
            "task_count": len(json.loads(r["tasks"])),
            "created_at": r["created_at"]
        }
        for r in rows
    ]


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Plan storage and retrieval")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # write
    write_parser = subparsers.add_parser("write", help="Store plan from stdin")

    # read
    read_parser = subparsers.add_parser("read", help="Get plan by ID")
    read_parser.add_argument("--id", type=int, required=True)

    # get-active
    subparsers.add_parser("get-active", help="Get most recent active plan")

    # mark-executed
    exec_parser = subparsers.add_parser("mark-executed", help="Mark plan as executed")
    exec_parser.add_argument("--id", type=int, required=True)

    # list
    list_parser = subparsers.add_parser("list", help="List plans")
    list_parser.add_argument("--status", help="Filter by status")

    args = parser.parse_args()

    if args.command == "write":
        plan_dict = json.load(sys.stdin)
        plan_id = write(plan_dict)
        print(json.dumps({"id": plan_id}))

    elif args.command == "read":
        result = read(args.id)
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"error": f"Plan {args.id} not found"}))
            sys.exit(1)

    elif args.command == "get-active":
        result = get_active()
        if result:
            print(json.dumps(result, indent=2))
        else:
            print(json.dumps({"error": "No active plan found"}))
            sys.exit(1)

    elif args.command == "mark-executed":
        if mark_executed(args.id):
            print(json.dumps({"status": "executed", "id": args.id}))
        else:
            print(json.dumps({"error": f"Plan {args.id} not found"}))
            sys.exit(1)

    elif args.command == "list":
        plans = list_plans(args.status)
        print(json.dumps(plans, indent=2))
