#!/usr/bin/env python3
"""Exploration module - context gathering for planning.

The explorer produces an Exploration, the planner consumes it.
This is the handoff contract between them.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from .db.connection import get_db, write_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock


def save(exploration: dict) -> dict:
    """Save exploration results.

    Args:
        exploration: Dict with keys:
            - objective: str
            - directories: dict
            - entry_points: list
            - test_patterns: list
            - framework: str | None
            - framework_confidence: float
            - idioms: dict
            - relevant_failures: list
            - relevant_patterns: list
            - target_files: list
            - target_functions: list

    Returns:
        {"id": int, "objective": str}
    """
    db = get_db()
    now = datetime.now().isoformat()
    objective = exploration.get("objective", "")

    with write_lock():
        cursor = db.execute(
            "INSERT INTO exploration (objective, data, created_at) VALUES (?, ?, ?)",
            (objective, json.dumps(exploration), now)
        )
        db.commit()
        return {"id": cursor.lastrowid, "objective": objective}


def load(exploration_id: Optional[int] = None) -> Optional[dict]:
    """Load exploration results.

    If no id provided, returns most recent.
    """
    db = get_db()

    if exploration_id:
        row = db.execute(
            "SELECT * FROM exploration WHERE id = ?", (exploration_id,)
        ).fetchone()
    else:
        row = db.execute(
            "SELECT * FROM exploration ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        return None

    data = json.loads(row["data"])
    data["_id"] = row["id"]
    data["_created_at"] = row["created_at"]
    return data


def clear() -> dict:
    """Clear all explorations."""
    db = get_db()
    with write_lock():
        db.execute("DELETE FROM exploration")
        db.commit()
    return {"status": "cleared"}


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix exploration operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # save (reads from stdin)
    subparsers.add_parser("save", help="Save exploration (reads JSON from stdin)")

    # load
    p = subparsers.add_parser("load")
    p.add_argument("--id", type=int, default=None)

    # clear
    subparsers.add_parser("clear")

    args = parser.parse_args()

    if args.command == "save":
        data = json.load(sys.stdin)
        result = save(data)
    elif args.command == "load":
        result = load(args.id)
        if result is None:
            result = {"error": "No exploration found"}
    elif args.command == "clear":
        result = clear()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
