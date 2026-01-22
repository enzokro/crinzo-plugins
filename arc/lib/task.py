#!/usr/bin/env python3
"""Task management for multi-step work.

Simple model:
- A session has one or more tasks
- Tasks track: objective, delta (files), status, injected memories, utilized memories
- Automatic feedback on completion
"""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .db.connection import get_db, write_lock
    from . import memory
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock
    import memory


def create_session() -> str:
    """Create a new session ID."""
    return uuid.uuid4().hex[:8]


def add(
    session_id: str,
    seq: int,
    objective: str,
    delta: List[str] = None,
    injected: List[str] = None
) -> dict:
    """Add a task to a session.

    Args:
        session_id: Session this task belongs to
        seq: Sequence number (for ordering)
        objective: What this task should accomplish
        delta: Files this task can modify
        injected: Memory names that were injected for this task
    """
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        db.execute(
            """INSERT INTO task (session_id, seq, objective, delta, injected, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, seq, objective, json.dumps(delta or []), json.dumps(injected or []), now)
        )
        db.commit()

    return {"session_id": session_id, "seq": seq, "status": "pending"}


def complete(session_id: str, seq: int, delivered: str, utilized: List[str] = None) -> dict:
    """Mark task complete and trigger feedback.

    Args:
        session_id: Session ID
        seq: Task sequence number
        delivered: What was delivered
        utilized: Memory names that actually helped

    This automatically triggers the feedback loop.
    """
    utilized = utilized or []
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        # Get task to find injected memories
        row = db.execute(
            "SELECT injected FROM task WHERE session_id=? AND seq=?",
            (session_id, seq)
        ).fetchone()

        if not row:
            return {"error": "task not found"}

        injected = json.loads(row["injected"]) if row["injected"] else []

        # Update task
        db.execute(
            "UPDATE task SET status='complete', delivered=?, utilized=?, completed_at=? WHERE session_id=? AND seq=?",
            (delivered, json.dumps(utilized), now, session_id, seq)
        )
        db.commit()

    # Close the feedback loop automatically
    if injected:
        fb = memory.feedback(utilized, injected)
    else:
        fb = {"helped": 0, "unhelpful": 0, "missing": []}

    return {"status": "complete", "feedback": fb}


def block(session_id: str, seq: int, reason: str, utilized: List[str] = None) -> dict:
    """Mark task blocked.

    Args:
        session_id: Session ID
        seq: Task sequence number
        reason: Why it was blocked
        utilized: Memory names that were still helpful

    This also triggers feedback (even failures provide signal).
    """
    utilized = utilized or []
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        row = db.execute(
            "SELECT injected FROM task WHERE session_id=? AND seq=?",
            (session_id, seq)
        ).fetchone()

        if not row:
            return {"error": "task not found"}

        injected = json.loads(row["injected"]) if row["injected"] else []

        db.execute(
            "UPDATE task SET status='blocked', delivered=?, utilized=?, completed_at=? WHERE session_id=? AND seq=?",
            (f"BLOCKED: {reason}", json.dumps(utilized), now, session_id, seq)
        )
        db.commit()

    # Feedback even on block
    if injected:
        fb = memory.feedback(utilized, injected)
    else:
        fb = {"helped": 0, "unhelpful": 0, "missing": []}

    return {"status": "blocked", "reason": reason, "feedback": fb}


def get(session_id: str, seq: Optional[int] = None) -> Optional[dict]:
    """Get task(s) by session and optionally seq."""
    db = get_db()

    if seq is not None:
        row = db.execute(
            "SELECT * FROM task WHERE session_id=? AND seq=?",
            (session_id, seq)
        ).fetchone()
        return _to_dict(row) if row else None

    rows = db.execute(
        "SELECT * FROM task WHERE session_id=? ORDER BY seq",
        (session_id,)
    ).fetchall()
    return [_to_dict(r) for r in rows]


def pending(session_id: str) -> List[dict]:
    """Get pending tasks for a session."""
    db = get_db()
    rows = db.execute(
        "SELECT * FROM task WHERE session_id=? AND status='pending' ORDER BY seq",
        (session_id,)
    ).fetchall()
    return [_to_dict(r) for r in rows]


def summary(session_id: str) -> dict:
    """Get summary of session tasks."""
    db = get_db()
    rows = db.execute("SELECT status, COUNT(*) as c FROM task WHERE session_id=? GROUP BY status", (session_id,)).fetchall()

    counts = {"pending": 0, "complete": 0, "blocked": 0}
    for r in rows:
        counts[r["status"]] = r["c"]

    return {
        "session_id": session_id,
        "total": sum(counts.values()),
        **counts
    }


def _to_dict(row) -> dict:
    return {
        "session_id": row["session_id"],
        "seq": row["seq"],
        "objective": row["objective"],
        "delta": json.loads(row["delta"]) if row["delta"] else [],
        "status": row["status"],
        "delivered": row["delivered"],
        "injected": json.loads(row["injected"]) if row["injected"] else [],
        "utilized": json.loads(row["utilized"]) if row["utilized"] else [],
        "created_at": row["created_at"],
        "completed_at": row["completed_at"]
    }


# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("new-session")

    s = sub.add_parser("add")
    s.add_argument("--session", required=True)
    s.add_argument("--seq", type=int, required=True)
    s.add_argument("--objective", required=True)
    s.add_argument("--delta", default="[]")
    s.add_argument("--injected", default="[]")

    s = sub.add_parser("complete")
    s.add_argument("--session", required=True)
    s.add_argument("--seq", type=int, required=True)
    s.add_argument("--delivered", required=True)
    s.add_argument("--utilized", default="[]")

    s = sub.add_parser("block")
    s.add_argument("--session", required=True)
    s.add_argument("--seq", type=int, required=True)
    s.add_argument("--reason", required=True)
    s.add_argument("--utilized", default="[]")

    s = sub.add_parser("get")
    s.add_argument("--session", required=True)
    s.add_argument("--seq", type=int, default=None)

    s = sub.add_parser("pending")
    s.add_argument("--session", required=True)

    s = sub.add_parser("summary")
    s.add_argument("--session", required=True)

    args = p.parse_args()

    if args.cmd == "new-session":
        r = {"session_id": create_session()}
    elif args.cmd == "add":
        r = add(args.session, args.seq, args.objective, json.loads(args.delta), json.loads(args.injected))
    elif args.cmd == "complete":
        r = complete(args.session, args.seq, args.delivered, json.loads(args.utilized))
    elif args.cmd == "block":
        r = block(args.session, args.seq, args.reason, json.loads(args.utilized))
    elif args.cmd == "get":
        r = get(args.session, args.seq)
        if r is None:
            r = {"error": "not found"}
    elif args.cmd == "pending":
        r = pending(args.session)
    elif args.cmd == "summary":
        r = summary(args.session)

    print(json.dumps(r, indent=2))
