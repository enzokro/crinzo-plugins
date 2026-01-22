#!/usr/bin/env python3
"""Metacognition: thinking about thinking.

This implements the metacognitive layer from cognitive architecture research.
The key insight: agents need to monitor their own reasoning processes and
recognize when their current approach isn't working.

Core functions:
- assess_approach(session_id) → is current approach working?
- should_pivot(session_id) → recommendation to change strategy
- record_outcome(session_id, task_seq, success, notes) → track results
- session_summary(session_id) → what happened, what worked

The Ralph Wiggum insight applies here: sometimes the best move is to
start fresh with a clean context rather than accumulate errors.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .db.connection import get_db, write_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock


# Thresholds for metacognitive decisions
FAILURE_THRESHOLD = 3  # consecutive failures before suggesting pivot
SUCCESS_RATE_THRESHOLD = 0.4  # below this, approach isn't working
MIN_TASKS_FOR_ASSESSMENT = 2  # need this many completed to assess


def _ensure_meta_table():
    """Create meta tracking table if not exists."""
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS meta_outcomes (
            id INTEGER PRIMARY KEY,
            session_id TEXT NOT NULL,
            task_seq INTEGER NOT NULL,
            success INTEGER NOT NULL,
            notes TEXT,
            recorded_at TEXT NOT NULL,
            UNIQUE(session_id, task_seq)
        )
    """)
    db.commit()


def record_outcome(
    session_id: str,
    task_seq: int,
    success: bool,
    notes: str = ""
) -> dict:
    """Record task outcome for metacognitive tracking."""
    _ensure_meta_table()
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                "INSERT INTO meta_outcomes (session_id, task_seq, success, notes, recorded_at) VALUES (?,?,?,?,?)",
                (session_id, task_seq, 1 if success else 0, notes, now)
            )
            db.commit()
            return {"status": "recorded"}
        except Exception as e:
            if "UNIQUE" in str(e):
                # Update existing
                db.execute(
                    "UPDATE meta_outcomes SET success=?, notes=?, recorded_at=? WHERE session_id=? AND task_seq=?",
                    (1 if success else 0, notes, now, session_id, task_seq)
                )
                db.commit()
                return {"status": "updated"}
            raise


def assess_approach(session_id: str) -> dict:
    """Assess whether current approach is working.

    Returns assessment with:
    - status: healthy | struggling | failing
    - success_rate: ratio of successful tasks
    - consecutive_failures: how many in a row
    - recommendation: keep_going | slow_down | consider_pivot | pivot_now
    """
    _ensure_meta_table()
    db = get_db()

    rows = db.execute(
        "SELECT success, notes FROM meta_outcomes WHERE session_id=? ORDER BY task_seq",
        (session_id,)
    ).fetchall()

    if not rows:
        return {
            "status": "no_data",
            "success_rate": None,
            "consecutive_failures": 0,
            "recommendation": "keep_going",
            "reason": "No outcomes recorded yet"
        }

    total = len(rows)
    successes = sum(1 for r in rows if r["success"])
    success_rate = successes / total if total > 0 else 0

    # Count consecutive failures from end
    consecutive_failures = 0
    for r in reversed(rows):
        if r["success"]:
            break
        consecutive_failures += 1

    # Determine status and recommendation
    if consecutive_failures >= FAILURE_THRESHOLD:
        status = "failing"
        recommendation = "pivot_now"
        reason = f"{consecutive_failures} consecutive failures - current approach is not working"
    elif success_rate < SUCCESS_RATE_THRESHOLD and total >= MIN_TASKS_FOR_ASSESSMENT:
        status = "struggling"
        recommendation = "consider_pivot"
        reason = f"Success rate {success_rate:.0%} is below threshold - approach may need adjustment"
    elif consecutive_failures > 0:
        status = "struggling"
        recommendation = "slow_down"
        reason = f"Recent failure(s) - proceed carefully"
    else:
        status = "healthy"
        recommendation = "keep_going"
        reason = "Approach appears to be working"

    return {
        "status": status,
        "success_rate": round(success_rate, 3),
        "total_tasks": total,
        "successes": successes,
        "consecutive_failures": consecutive_failures,
        "recommendation": recommendation,
        "reason": reason
    }


def should_pivot(session_id: str) -> dict:
    """Explicit recommendation on whether to change approach.

    The Ralph insight: sometimes starting fresh is better than
    accumulating context rot.
    """
    assessment = assess_approach(session_id)

    if assessment["recommendation"] == "pivot_now":
        return {
            "should_pivot": True,
            "confidence": "high",
            "suggestion": "Start fresh with a different approach. Current path has repeatedly failed.",
            "options": [
                "Simplify the objective",
                "Try a completely different approach",
                "Ask for clarification on requirements",
                "Start a new session with fresh context (Ralph pattern)"
            ]
        }
    elif assessment["recommendation"] == "consider_pivot":
        return {
            "should_pivot": "maybe",
            "confidence": "medium",
            "suggestion": "Current approach is struggling. Consider whether to continue or try something different.",
            "options": [
                "Continue with increased caution",
                "Review what's not working before proceeding",
                "Adjust approach based on failure patterns"
            ]
        }
    else:
        return {
            "should_pivot": False,
            "confidence": "high" if assessment["status"] == "healthy" else "medium",
            "suggestion": "Current approach appears viable. Continue."
        }


def session_summary(session_id: str) -> dict:
    """Get summary of session for learning extraction."""
    _ensure_meta_table()
    db = get_db()

    rows = db.execute(
        "SELECT task_seq, success, notes, recorded_at FROM meta_outcomes WHERE session_id=? ORDER BY task_seq",
        (session_id,)
    ).fetchall()

    if not rows:
        return {"session_id": session_id, "tasks": [], "summary": "No outcomes recorded"}

    tasks = []
    for r in rows:
        tasks.append({
            "seq": r["task_seq"],
            "success": bool(r["success"]),
            "notes": r["notes"],
            "recorded_at": r["recorded_at"]
        })

    total = len(tasks)
    successes = sum(1 for t in tasks if t["success"])

    # Identify patterns
    failure_notes = [t["notes"] for t in tasks if not t["success"] and t["notes"]]
    success_notes = [t["notes"] for t in tasks if t["success"] and t["notes"]]

    return {
        "session_id": session_id,
        "total_tasks": total,
        "successes": successes,
        "success_rate": round(successes / total, 3) if total > 0 else 0,
        "tasks": tasks,
        "failure_notes": failure_notes,
        "success_notes": success_notes
    }


def clear_session(session_id: str) -> dict:
    """Clear metacognitive data for a session (Ralph reset)."""
    _ensure_meta_table()
    db = get_db()

    with write_lock():
        result = db.execute("DELETE FROM meta_outcomes WHERE session_id=?", (session_id,))
        db.commit()

    return {"cleared": result.rowcount}


# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("record")
    s.add_argument("--session", required=True)
    s.add_argument("--seq", type=int, required=True)
    s.add_argument("--success", action="store_true")
    s.add_argument("--notes", default="")

    s = sub.add_parser("assess")
    s.add_argument("--session", required=True)

    s = sub.add_parser("should-pivot")
    s.add_argument("--session", required=True)

    s = sub.add_parser("summary")
    s.add_argument("--session", required=True)

    s = sub.add_parser("clear")
    s.add_argument("--session", required=True)

    args = p.parse_args()

    if args.cmd == "record":
        r = record_outcome(args.session, args.seq, args.success, args.notes)
    elif args.cmd == "assess":
        r = assess_approach(args.session)
    elif args.cmd == "should-pivot":
        r = should_pivot(args.session)
    elif args.cmd == "summary":
        r = session_summary(args.session)
    elif args.cmd == "clear":
        r = clear_session(args.session)

    print(json.dumps(r, indent=2))
