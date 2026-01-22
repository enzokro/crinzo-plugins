#!/usr/bin/env python3
"""Memory: the persistence layer for learning.

Simple API:
- store(trigger, resolution, type) → name
- recall(query, limit) → memories with relevance
- feedback(utilized, injected) → closes the loop
- relate(a, b, type) → creates connection
- connected(name) → related memories
- prune() → removes ineffective memories
- health() → system status
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

try:
    from .db.connection import get_db, write_lock
    from .db.embeddings import embed, to_blob, from_blob, cosine, is_available
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock
    from db.embeddings import embed, to_blob, from_blob, cosine, is_available


DUPLICATE_THRESHOLD = 0.85


def _slug(text: str) -> str:
    """Create kebab-case slug."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] if len(s) > 50 else s


def _effectiveness(row) -> float:
    """Calculate effectiveness from helped/failed."""
    h, f = row["helped"] or 0, row["failed"] or 0
    return h / (h + f) if (h + f) > 0 else 0.5


def store(
    trigger: str,
    resolution: str,
    type: str = "failure",
    source: str = ""
) -> dict:
    """Store a memory. Returns {status, name, reason}."""

    if type not in ("failure", "pattern"):
        return {"status": "rejected", "name": "", "reason": "type must be failure or pattern"}

    if len(trigger.strip()) < 10:
        return {"status": "rejected", "name": "", "reason": "trigger too short"}

    if not resolution.strip():
        return {"status": "rejected", "name": "", "reason": "resolution empty"}

    # Check for semantic duplicate
    if is_available():
        new_emb = embed(trigger)
        if new_emb:
            db = get_db()
            for row in db.execute("SELECT name, embedding FROM memory WHERE type=? AND embedding IS NOT NULL", (type,)):
                if cosine(new_emb, from_blob(row["embedding"])) >= DUPLICATE_THRESHOLD:
                    return {"status": "merged", "name": row["name"], "reason": "similar exists"}

    name = _slug(trigger)
    if not name:
        name = f"{type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    emb_blob = None
    e = embed(trigger + " " + resolution)
    if e:
        emb_blob = to_blob(e)

    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source) VALUES (?,?,?,?,?,?,?)",
                (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source) VALUES (?,?,?,?,?,?,?)",
                    (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def recall(
    query: str,
    type: Optional[str] = None,
    limit: int = 5,
    min_effectiveness: float = 0.0
) -> List[dict]:
    """Recall memories by semantic similarity. Returns list with _relevance scores."""

    db = get_db()
    sql = "SELECT * FROM memory WHERE embedding IS NOT NULL"
    params = []
    if type:
        sql += " AND type=?"
        params.append(type)

    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    q_emb = embed(query)
    if q_emb is None:
        # Fallback: by effectiveness
        rows = db.execute(
            f"SELECT * FROM memory {'WHERE type=?' if type else ''} ORDER BY (helped*1.0/(helped+failed+1)) DESC LIMIT ?",
            ([type, limit] if type else [limit])
        ).fetchall()
        return [_to_dict(r) for r in rows]

    scored = []
    for r in rows:
        eff = _effectiveness(r)
        if eff < min_effectiveness:
            continue
        rel = cosine(q_emb, from_blob(r["embedding"]))
        score = rel * (0.7 + 0.3 * eff)  # relevance matters most, effectiveness boosts
        m = _to_dict(r)
        m["_relevance"] = round(rel, 3)
        m["_score"] = round(score, 3)
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


def feedback(utilized: List[str], injected: List[str]) -> dict:
    """Update effectiveness based on what was actually used.

    This is THE critical function that closes the learning loop.
    """
    db = get_db()
    now = datetime.now().isoformat()
    helped = 0
    unhelpful = 0
    missing = []

    util_set = set(utilized)
    inj_set = set(injected)

    with write_lock():
        for name in inj_set:
            row = db.execute("SELECT id FROM memory WHERE name=?", (name,)).fetchone()
            if not row:
                missing.append(name)
                continue

            if name in util_set:
                db.execute("UPDATE memory SET helped=helped+1, last_used=? WHERE name=?", (now, name))
                helped += 1
            else:
                db.execute("UPDATE memory SET failed=failed+1 WHERE name=?", (name,))
                unhelpful += 1

        db.commit()

    return {"helped": helped, "unhelpful": unhelpful, "missing": missing}


def relate(from_name: str, to_name: str, rel_type: str, weight: float = 1.0) -> dict:
    """Create relationship between memories."""
    db = get_db()

    for n in [from_name, to_name]:
        if not db.execute("SELECT 1 FROM memory WHERE name=?", (n,)).fetchone():
            return {"status": "rejected", "reason": f"memory not found: {n}"}

    now = datetime.now().isoformat()
    with write_lock():
        try:
            db.execute(
                "INSERT INTO edge (from_name, to_name, rel_type, weight, created_at) VALUES (?,?,?,?,?)",
                (from_name, to_name, rel_type, weight, now)
            )
            db.commit()
            return {"status": "added"}
        except:
            return {"status": "exists"}


def connected(name: str, max_hops: int = 2) -> List[dict]:
    """Find connected memories via graph traversal."""
    db = get_db()
    if not db.execute("SELECT 1 FROM memory WHERE name=?", (name,)).fetchone():
        return []

    visited = {name}
    results = []
    frontier = [name]

    for hop in range(1, max_hops + 1):
        next_frontier = []
        for current in frontier:
            edges = db.execute(
                "SELECT to_name, rel_type, weight FROM edge WHERE from_name=? UNION SELECT from_name, rel_type, weight FROM edge WHERE to_name=?",
                (current, current)
            ).fetchall()

            for e in edges:
                neighbor = e["to_name"] if e["to_name"] != current else e["from_name"]
                if neighbor in visited or e["weight"] < 0.5:
                    continue
                visited.add(neighbor)
                next_frontier.append(neighbor)

                row = db.execute("SELECT * FROM memory WHERE name=?", (neighbor,)).fetchone()
                if row:
                    m = _to_dict(row)
                    m["_hop"] = hop
                    m["_via"] = e["rel_type"]
                    results.append(m)

        frontier = next_frontier

    return results


def prune(min_effectiveness: float = 0.25, min_uses: int = 3) -> dict:
    """Remove memories that have proven unhelpful."""
    db = get_db()
    rows = db.execute("SELECT name, helped, failed FROM memory WHERE (helped+failed)>=?", (min_uses,)).fetchall()

    to_remove = []
    for r in rows:
        if _effectiveness(r) < min_effectiveness:
            to_remove.append(r["name"])

    with write_lock():
        for n in to_remove:
            db.execute("DELETE FROM memory WHERE name=?", (n,))
            db.execute("DELETE FROM edge WHERE from_name=? OR to_name=?", (n, n))
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    return {"pruned": len(to_remove), "remaining": remaining}


def health() -> dict:
    """Check learning system health."""
    db = get_db()

    total = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    by_type = {}
    for row in db.execute("SELECT type, COUNT(*) as c, SUM(helped) as h, SUM(failed) as f FROM memory GROUP BY type"):
        by_type[row["type"]] = {"count": row["c"], "helped": row["h"] or 0, "failed": row["f"] or 0}

    with_feedback = db.execute("SELECT COUNT(*) as c FROM memory WHERE (helped+failed)>0").fetchone()["c"]
    edges = db.execute("SELECT COUNT(*) as c FROM edge").fetchone()["c"]

    total_h = sum(t["helped"] for t in by_type.values())
    total_f = sum(t["failed"] for t in by_type.values())
    effectiveness = total_h / (total_h + total_f) if (total_h + total_f) > 0 else 0.5

    loop_closed = total > 0 and with_feedback > 0
    issues = []
    if total == 0:
        issues.append("No memories yet")
    elif with_feedback == 0:
        issues.append("No feedback recorded - learning loop not closed")
    if not is_available():
        issues.append("Embeddings unavailable - install sentence-transformers")

    return {
        "status": "HEALTHY" if loop_closed and not issues else "NEEDS_ATTENTION",
        "total": total,
        "by_type": by_type,
        "effectiveness": round(effectiveness, 3),
        "with_feedback": with_feedback,
        "relationships": edges,
        "issues": issues
    }


def get(name: str) -> Optional[dict]:
    """Get specific memory by name."""
    db = get_db()
    row = db.execute("SELECT * FROM memory WHERE name=?", (name,)).fetchone()
    return _to_dict(row) if row else None


def _to_dict(row) -> dict:
    return {
        "name": row["name"],
        "type": row["type"],
        "trigger": row["trigger"],
        "resolution": row["resolution"],
        "helped": row["helped"] or 0,
        "failed": row["failed"] or 0,
        "effectiveness": round(_effectiveness(row), 3),
        "created_at": row["created_at"],
        "source": row["source"]
    }


# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("store")
    s.add_argument("--trigger", required=True)
    s.add_argument("--resolution", required=True)
    s.add_argument("--type", default="failure")
    s.add_argument("--source", default="")

    s = sub.add_parser("recall")
    s.add_argument("query")
    s.add_argument("--type", default=None)
    s.add_argument("--limit", type=int, default=5)

    s = sub.add_parser("feedback")
    s.add_argument("--utilized", required=True)
    s.add_argument("--injected", required=True)

    s = sub.add_parser("relate")
    s.add_argument("--from", dest="from_name", required=True)
    s.add_argument("--to", dest="to_name", required=True)
    s.add_argument("--type", dest="rel_type", required=True)

    s = sub.add_parser("connected")
    s.add_argument("name")

    sub.add_parser("prune")
    sub.add_parser("health")

    s = sub.add_parser("get")
    s.add_argument("name")

    args = p.parse_args()

    if args.cmd == "store":
        r = store(args.trigger, args.resolution, args.type, args.source)
    elif args.cmd == "recall":
        r = recall(args.query, args.type, args.limit)
    elif args.cmd == "feedback":
        r = feedback(json.loads(args.utilized), json.loads(args.injected))
    elif args.cmd == "relate":
        r = relate(args.from_name, args.to_name, args.rel_type)
    elif args.cmd == "connected":
        r = connected(args.name)
    elif args.cmd == "prune":
        r = prune()
    elif args.cmd == "health":
        r = health()
    elif args.cmd == "get":
        r = get(args.name)
        if r is None:
            r = {"error": "not found"}

    print(json.dumps(r, indent=2))
