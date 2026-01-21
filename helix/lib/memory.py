#!/usr/bin/env python3
"""Enhanced memory module with graph relationships.

Core operations:
1. add()       - Store knowledge with semantic deduplication
2. query()     - Retrieve by meaning, ranked by relevance × effectiveness
3. feedback()  - Update effectiveness based on utilization
4. relate()    - Create relationships between memories
5. related()   - Graph traversal for connected knowledge
6. prune()     - Remove ineffective memories
7. stats()     - Health metrics
8. verify()    - Check loop closure
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Support both module and script execution
try:
    from .db.connection import get_db, write_lock
    from .db.embeddings import (
        embed, embed_to_blob, blob_to_embed,
        cosine_similarity, is_available as embeddings_available,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock
    from db.embeddings import (
        embed, embed_to_blob, blob_to_embed,
        cosine_similarity, is_available as embeddings_available,
    )

# Thresholds
DUPLICATE_THRESHOLD = 0.85
MIN_TRIGGER_LENGTH = 10
DEFAULT_PRUNE_THRESHOLD = 0.25
MAX_HOPS = 2
MIN_WEIGHT = 0.5


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:50] if len(slug) > 50 else slug


def _find_duplicate(trigger: str, memory_type: str) -> Optional[str]:
    """Find existing memory with similar trigger."""
    if not embeddings_available():
        return None

    db = get_db()
    cursor = db.execute(
        "SELECT name, embedding FROM memory WHERE type = ? AND embedding IS NOT NULL",
        (memory_type,)
    )

    new_emb = embed(trigger)
    if new_emb is None:
        return None

    for row in cursor:
        existing_emb = blob_to_embed(row["embedding"])
        if cosine_similarity(new_emb, existing_emb) >= DUPLICATE_THRESHOLD:
            return row["name"]

    return None


def add(
    trigger: str,
    resolution: str,
    memory_type: str = "failure",
    source: str = "",
    name: Optional[str] = None,
) -> dict:
    """Store a new memory with semantic deduplication.

    Returns: {"status": "added"|"merged"|"rejected", "name": str, "reason": str}
    """
    if memory_type not in ("failure", "pattern"):
        return {"status": "rejected", "name": "", "reason": f"Invalid type: {memory_type}"}

    if len(trigger.strip()) < MIN_TRIGGER_LENGTH:
        return {"status": "rejected", "name": "", "reason": f"Trigger too short"}

    if not resolution.strip():
        return {"status": "rejected", "name": "", "reason": "Resolution empty"}

    # Check for duplicate
    existing = _find_duplicate(trigger, memory_type)
    if existing:
        return {"status": "merged", "name": existing, "reason": f"Similar to: {existing}"}

    # Generate name
    if not name:
        name = _slugify(trigger[:50])
        if not name:
            name = f"{memory_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Generate embedding
    emb_blob = None
    emb = embed(trigger + " " + resolution)
    if emb:
        emb_blob = embed_to_blob(emb)

    # Insert
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                """INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (name, memory_type, trigger.strip(), resolution.strip(), emb_blob, now, source)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    """INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (name, memory_type, trigger.strip(), resolution.strip(), emb_blob, now, source)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def query(
    text: str,
    memory_type: Optional[str] = None,
    limit: int = 5,
    min_effectiveness: float = 0.0,
) -> List[dict]:
    """Retrieve memories by semantic similarity.

    Returns list sorted by relevance × effectiveness.
    """
    db = get_db()

    sql = "SELECT * FROM memory WHERE embedding IS NOT NULL"
    params = []

    if memory_type:
        sql += " AND type = ?"
        params.append(memory_type)

    rows = db.execute(sql, params).fetchall()

    if not rows:
        return []

    query_emb = embed(text)
    if query_emb is None:
        # Fallback: return by effectiveness
        sql = "SELECT * FROM memory"
        if memory_type:
            sql += f" WHERE type = '{memory_type}'"
        sql += " ORDER BY (helped * 1.0 / (helped + failed + 1)) DESC LIMIT ?"
        rows = db.execute(sql, (limit,)).fetchall()
        return [_row_to_dict(r) for r in rows]

    # Score by relevance × effectiveness
    scored = []
    for row in rows:
        mem = _row_to_dict(row)

        # Relevance
        row_emb = blob_to_embed(row["embedding"])
        relevance = cosine_similarity(query_emb, row_emb)

        # Effectiveness
        effectiveness = mem["effectiveness"]

        if effectiveness < min_effectiveness:
            continue

        # Combined score
        score = relevance * (0.7 + 0.3 * effectiveness)

        mem["_relevance"] = round(relevance, 3)
        mem["_score"] = round(score, 3)
        scored.append((score, mem))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:limit]]


def feedback(utilized: List[str], injected: List[str]) -> dict:
    """Update memory effectiveness based on utilization.

    This closes the learning loop.
    """
    db = get_db()
    now = datetime.now().isoformat()
    helped_count = 0
    not_helped_count = 0
    not_found = []

    utilized_set = set(utilized)
    injected_set = set(injected)

    with write_lock():
        for name in injected_set:
            row = db.execute("SELECT id FROM memory WHERE name = ?", (name,)).fetchone()

            if not row:
                not_found.append(name)
                continue

            if name in utilized_set:
                db.execute(
                    "UPDATE memory SET helped = helped + 1, last_used = ? WHERE name = ?",
                    (now, name)
                )
                helped_count += 1
            else:
                db.execute("UPDATE memory SET failed = failed + 1 WHERE name = ?", (name,))
                not_helped_count += 1

        db.commit()

    return {"helped": helped_count, "not_helped": not_helped_count, "not_found": not_found}


def relate(from_name: str, to_name: str, rel_type: str, weight: float = 1.0) -> dict:
    """Create a relationship between two memories.

    rel_type: co_occurs, causes, solves, similar
    """
    valid_types = {"co_occurs", "causes", "solves", "similar"}
    if rel_type not in valid_types:
        return {"status": "rejected", "reason": f"Invalid rel_type: {rel_type}"}

    db = get_db()

    # Verify both memories exist
    for name in [from_name, to_name]:
        if not db.execute("SELECT 1 FROM memory WHERE name = ?", (name,)).fetchone():
            return {"status": "rejected", "reason": f"Memory not found: {name}"}

    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                """INSERT INTO memory_edge (from_name, to_name, rel_type, weight, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (from_name, to_name, rel_type, weight, now)
            )
            db.commit()
            return {"status": "added", "from": from_name, "to": to_name, "rel_type": rel_type}
        except Exception as e:
            if "UNIQUE" in str(e):
                return {"status": "exists", "from": from_name, "to": to_name, "rel_type": rel_type}
            raise


def related(name: str, max_hops: int = MAX_HOPS) -> List[dict]:
    """Find related memories via graph traversal (BFS)."""
    db = get_db()

    # Check memory exists
    if not db.execute("SELECT 1 FROM memory WHERE name = ?", (name,)).fetchone():
        return []

    visited = {name}
    results = []
    current_level = [name]

    for hop in range(1, max_hops + 1):
        next_level = []

        for current in current_level:
            # Get all edges from current
            edges = db.execute(
                """SELECT to_name, rel_type, weight FROM memory_edge WHERE from_name = ?
                   UNION
                   SELECT from_name, rel_type, weight FROM memory_edge WHERE to_name = ?""",
                (current, current)
            ).fetchall()

            for edge in edges:
                neighbor = edge["to_name"] if edge["to_name"] != current else edge["from_name"]

                if neighbor in visited:
                    continue

                if edge["weight"] < MIN_WEIGHT:
                    continue

                visited.add(neighbor)
                next_level.append(neighbor)

                # Get the memory
                mem_row = db.execute("SELECT * FROM memory WHERE name = ?", (neighbor,)).fetchone()
                if mem_row:
                    mem = _row_to_dict(mem_row)
                    mem["_hops"] = hop
                    mem["_via"] = edge["rel_type"]
                    mem["_weight"] = edge["weight"]
                    results.append(mem)

        current_level = next_level

    return results


def prune(min_effectiveness: float = DEFAULT_PRUNE_THRESHOLD, min_uses: int = 3) -> dict:
    """Remove memories that have proven ineffective."""
    db = get_db()

    rows = db.execute(
        "SELECT name, helped, failed FROM memory WHERE (helped + failed) >= ?",
        (min_uses,)
    ).fetchall()

    to_prune = []
    for row in rows:
        total = row["helped"] + row["failed"]
        effectiveness = row["helped"] / total if total > 0 else 0.5
        if effectiveness < min_effectiveness:
            to_prune.append(row["name"])

    with write_lock():
        for name in to_prune:
            db.execute("DELETE FROM memory WHERE name = ?", (name,))
            db.execute("DELETE FROM memory_edge WHERE from_name = ? OR to_name = ?", (name, name))
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]

    return {"pruned": len(to_prune), "remaining": remaining, "pruned_names": to_prune}


def stats() -> dict:
    """Get memory health statistics."""
    db = get_db()

    cursor = db.execute("""
        SELECT
            type,
            COUNT(*) as count,
            SUM(helped) as total_helped,
            SUM(failed) as total_failed,
            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embedding
        FROM memory GROUP BY type
    """)

    by_type = {}
    total = 0
    total_helped = 0
    total_failed = 0
    total_with_emb = 0

    for row in cursor:
        by_type[row["type"]] = {
            "count": row["count"],
            "total_helped": row["total_helped"] or 0,
            "total_failed": row["total_failed"] or 0,
            "with_embedding": row["with_embedding"],
        }
        total += row["count"]
        total_helped += row["total_helped"] or 0
        total_failed += row["total_failed"] or 0
        total_with_emb += row["with_embedding"]

    total_uses = total_helped + total_failed
    overall_effectiveness = total_helped / total_uses if total_uses > 0 else 0.5

    with_feedback = db.execute(
        "SELECT COUNT(*) as c FROM memory WHERE (helped + failed) > 0"
    ).fetchone()["c"]

    edge_count = db.execute("SELECT COUNT(*) as c FROM memory_edge").fetchone()["c"]

    return {
        "total": total,
        "by_type": by_type,
        "total_helped": total_helped,
        "total_failed": total_failed,
        "overall_effectiveness": round(overall_effectiveness, 3),
        "with_feedback": with_feedback,
        "without_feedback": total - with_feedback,
        "embedding_coverage": round(total_with_emb / total, 3) if total > 0 else 0,
        "relationships": edge_count,
        "embeddings_available": embeddings_available(),
    }


def verify() -> dict:
    """Verify the learning loop is closed."""
    s = stats()
    issues = []
    checks = {}

    checks["memories_exist"] = s["total"] > 0
    if not checks["memories_exist"]:
        issues.append("No memories - run some tasks first")

    checks["has_feedback"] = s["with_feedback"] > 0
    if s["total"] > 0 and not checks["has_feedback"]:
        issues.append("No feedback recorded - ensure UTILIZED tracking works")

    checks["embeddings_available"] = s["embeddings_available"]
    if not checks["embeddings_available"]:
        issues.append("Embeddings unavailable - install sentence-transformers")

    checks["good_coverage"] = s["embedding_coverage"] >= 0.8 if s["total"] > 0 else True
    if s["total"] > 0 and not checks["good_coverage"]:
        issues.append(f"Low embedding coverage ({s['embedding_coverage']:.0%})")

    status = "CLOSED" if checks.get("memories_exist") and checks.get("has_feedback") else "OPEN"

    return {"status": status, "checks": checks, "issues": issues, "stats": s}


def get_by_name(name: str) -> Optional[dict]:
    """Get a specific memory by name."""
    db = get_db()
    row = db.execute("SELECT * FROM memory WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row) if row else None


def _row_to_dict(row) -> dict:
    """Convert database row to memory dict."""
    total = (row["helped"] or 0) + (row["failed"] or 0)
    effectiveness = (row["helped"] or 0) / total if total > 0 else 0.5

    return {
        "id": row["id"],
        "name": row["name"],
        "type": row["type"],
        "trigger": row["trigger"],
        "resolution": row["resolution"],
        "helped": row["helped"] or 0,
        "failed": row["failed"] or 0,
        "effectiveness": round(effectiveness, 3),
        "total_uses": total,
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "source": row["source"],
    }


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix memory operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    p = subparsers.add_parser("add")
    p.add_argument("--trigger", required=True)
    p.add_argument("--resolution", required=True)
    p.add_argument("--type", choices=["failure", "pattern"], default="failure")
    p.add_argument("--source", default="")
    p.add_argument("--name", default=None)

    # query
    p = subparsers.add_parser("query")
    p.add_argument("text")
    p.add_argument("--type", choices=["failure", "pattern"], default=None)
    p.add_argument("--limit", type=int, default=5)

    # feedback
    p = subparsers.add_parser("feedback")
    p.add_argument("--utilized", required=True)
    p.add_argument("--injected", required=True)

    # relate
    p = subparsers.add_parser("relate")
    p.add_argument("--from", dest="from_name", required=True)
    p.add_argument("--to", dest="to_name", required=True)
    p.add_argument("--rel-type", required=True)
    p.add_argument("--weight", type=float, default=1.0)

    # related
    p = subparsers.add_parser("related")
    p.add_argument("name")
    p.add_argument("--max-hops", type=int, default=2)

    # prune
    p = subparsers.add_parser("prune")
    p.add_argument("--min-effectiveness", type=float, default=0.25)
    p.add_argument("--min-uses", type=int, default=3)

    # stats
    subparsers.add_parser("stats")

    # verify
    subparsers.add_parser("verify")

    # get
    p = subparsers.add_parser("get")
    p.add_argument("name")

    args = parser.parse_args()

    if args.command == "add":
        result = add(args.trigger, args.resolution, args.type, args.source, args.name)
    elif args.command == "query":
        result = query(args.text, args.type, args.limit)
    elif args.command == "feedback":
        result = feedback(json.loads(args.utilized), json.loads(args.injected))
    elif args.command == "relate":
        result = relate(args.from_name, args.to_name, args.rel_type, args.weight)
    elif args.command == "related":
        result = related(args.name, args.max_hops)
    elif args.command == "prune":
        result = prune(args.min_effectiveness, args.min_uses)
    elif args.command == "stats":
        result = stats()
    elif args.command == "verify":
        result = verify()
    elif args.command == "get":
        result = get_by_name(args.name)
        if result is None:
            result = {"error": f"Not found: {args.name}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
