#!/usr/bin/env python3
"""Core memory operations - the heart of the learning system.

This module implements the essential 6 operations:
1. add()      - Store knowledge (failures or patterns)
2. query()    - Retrieve by semantic meaning
3. feedback() - Update effectiveness based on utilization
4. prune()    - Remove ineffective memories
5. stats()    - Memory health metrics
6. verify()   - Check if learning loop is closed

The key insight: memories earn their place through demonstrated usefulness.
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Support both module and script execution
try:
    from .db.connection import get_db, write_lock
    from .db.schema import Memory
    from .db.embeddings import (
        embed,
        embed_to_blob,
        blob_to_embed,
        cosine_similarity,
        is_available as embeddings_available,
    )
except ImportError:
    # Running as script - add parent to path
    sys.path.insert(0, str(Path(__file__).parent))
    from db.connection import get_db, write_lock
    from db.schema import Memory
    from db.embeddings import (
        embed,
        embed_to_blob,
        blob_to_embed,
        cosine_similarity,
        is_available as embeddings_available,
    )

# Thresholds
DUPLICATE_THRESHOLD = 0.85      # merge if similarity > 85%
MIN_TRIGGER_LENGTH = 10         # reject triggers < 10 chars
DEFAULT_PRUNE_THRESHOLD = 0.25  # remove if effectiveness < 25%


def _slugify(text: str) -> str:
    """Convert text to kebab-case slug."""
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    # Remove leading/trailing hyphens and collapse multiple hyphens
    slug = re.sub(r"-+", "-", slug).strip("-")
    # Truncate to reasonable length
    return slug[:50] if len(slug) > 50 else slug


def _find_duplicate(trigger: str, memory_type: str) -> Optional[str]:
    """Find existing memory with similar trigger (semantic deduplication)."""
    if not embeddings_available():
        return None

    db = get_db()
    cursor = db.execute(
        "SELECT name, embedding FROM memory WHERE type = ? AND embedding IS NOT NULL",
        (memory_type,)
    )

    new_embedding = embed(trigger)
    if new_embedding is None:
        return None

    for row in cursor:
        existing_embedding = blob_to_embed(row["embedding"])
        sim = cosine_similarity(new_embedding, existing_embedding)
        if sim >= DUPLICATE_THRESHOLD:
            return row["name"]

    return None


def add(
    trigger: str,
    resolution: str,
    memory_type: str = "failure",
    source: str = "",
    name: Optional[str] = None,
) -> dict:
    """Store a new memory (failure or pattern).

    Args:
        trigger: When does this apply? (error message, situation)
        resolution: What do you do about it? (fix, technique)
        memory_type: "failure" or "pattern"
        source: Where did this come from? (task id, workspace)
        name: Optional explicit name (auto-generated if not provided)

    Returns:
        {"status": "added"|"merged"|"rejected", "name": str, "reason": str}
    """
    # Validate
    if memory_type not in ("failure", "pattern"):
        return {"status": "rejected", "name": "", "reason": f"Invalid type: {memory_type}"}

    if len(trigger.strip()) < MIN_TRIGGER_LENGTH:
        return {"status": "rejected", "name": "", "reason": f"Trigger too short (min {MIN_TRIGGER_LENGTH} chars)"}

    if not resolution.strip():
        return {"status": "rejected", "name": "", "reason": "Resolution cannot be empty"}

    # Check for semantic duplicate
    existing = _find_duplicate(trigger, memory_type)
    if existing:
        return {"status": "merged", "name": existing, "reason": f"Similar to existing: {existing}"}

    # Generate name if not provided
    if not name:
        name = _slugify(trigger[:50])
        if not name:
            name = f"{memory_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    # Generate embedding
    embedding_blob = None
    embedding_tuple = embed(trigger + " " + resolution)
    if embedding_tuple:
        embedding_blob = embed_to_blob(embedding_tuple)

    # Insert
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                """
                INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, memory_type, trigger.strip(), resolution.strip(), embedding_blob, now, source)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                # Name collision - append timestamp
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    """
                    INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (name, memory_type, trigger.strip(), resolution.strip(), embedding_blob, now, source)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def query(
    text: str,
    memory_type: Optional[str] = None,
    limit: int = 5,
    min_effectiveness: float = 0.0,
) -> list[dict]:
    """Retrieve memories by semantic similarity.

    Args:
        text: The query text (task description, error message)
        memory_type: Filter by "failure" or "pattern" (None for both)
        limit: Maximum number of results
        min_effectiveness: Minimum effectiveness threshold

    Returns:
        List of memory dicts with added "_relevance" field, sorted by relevance.
    """
    db = get_db()

    # Build query
    sql = "SELECT * FROM memory WHERE embedding IS NOT NULL"
    params = []

    if memory_type:
        sql += " AND type = ?"
        params.append(memory_type)

    cursor = db.execute(sql, params)
    rows = cursor.fetchall()

    if not rows:
        return []

    # Get query embedding
    query_embedding = embed(text)
    if query_embedding is None:
        # Fallback: return most effective memories
        sql = "SELECT * FROM memory"
        if memory_type:
            sql += " WHERE type = ?"
            params = [memory_type]
        else:
            params = []
        sql += " ORDER BY (helped * 1.0 / (helped + failed + 1)) DESC LIMIT ?"
        params.append(limit)
        cursor = db.execute(sql, params)
        rows = cursor.fetchall()
        return [_row_to_dict(row) for row in rows]

    # Score by relevance * effectiveness
    scored = []
    for row in rows:
        mem = _row_to_dict(row)

        # Calculate relevance (semantic similarity)
        row_embedding = blob_to_embed(row["embedding"])
        relevance = cosine_similarity(query_embedding, row_embedding)

        # Calculate effectiveness
        effectiveness = mem["effectiveness"]

        # Skip if below threshold
        if effectiveness < min_effectiveness:
            continue

        # Combined score: relevance matters most, effectiveness is a boost
        score = relevance * (0.7 + 0.3 * effectiveness)

        mem["_relevance"] = round(relevance, 3)
        mem["_score"] = round(score, 3)
        scored.append((score, mem))

    # Sort by score, return top results
    scored.sort(key=lambda x: x[0], reverse=True)
    return [mem for _, mem in scored[:limit]]


def feedback(utilized: list[str], injected: list[str]) -> dict:
    """Update memory effectiveness based on utilization.

    This closes the learning loop:
    - Memories that were used get boosted (helped++)
    - Memories that were injected but not used get penalized (failed++)

    Args:
        utilized: List of memory names that actually helped
        injected: List of memory names that were injected

    Returns:
        {"helped": int, "not_helped": int, "not_found": list}
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
            # Check if memory exists
            cursor = db.execute("SELECT id FROM memory WHERE name = ?", (name,))
            row = cursor.fetchone()

            if not row:
                not_found.append(name)
                continue

            if name in utilized_set:
                # This memory helped!
                db.execute(
                    "UPDATE memory SET helped = helped + 1, last_used = ? WHERE name = ?",
                    (now, name)
                )
                helped_count += 1
            else:
                # This memory was injected but not used
                db.execute(
                    "UPDATE memory SET failed = failed + 1 WHERE name = ?",
                    (name,)
                )
                not_helped_count += 1

        db.commit()

    return {
        "helped": helped_count,
        "not_helped": not_helped_count,
        "not_found": not_found,
    }


def prune(min_effectiveness: float = DEFAULT_PRUNE_THRESHOLD, min_uses: int = 3) -> dict:
    """Remove memories that have proven ineffective.

    Only prunes memories that have been used at least `min_uses` times,
    to avoid removing memories that haven't had a chance to prove themselves.

    Args:
        min_effectiveness: Remove if effectiveness below this threshold
        min_uses: Only consider memories with at least this many uses

    Returns:
        {"pruned": int, "remaining": int, "pruned_names": list}
    """
    db = get_db()

    # Find memories to prune
    cursor = db.execute(
        """
        SELECT name, helped, failed
        FROM memory
        WHERE (helped + failed) >= ?
        """,
        (min_uses,)
    )

    to_prune = []
    for row in cursor:
        total = row["helped"] + row["failed"]
        effectiveness = row["helped"] / total if total > 0 else 0.5
        if effectiveness < min_effectiveness:
            to_prune.append(row["name"])

    # Delete
    with write_lock():
        for name in to_prune:
            db.execute("DELETE FROM memory WHERE name = ?", (name,))
        db.commit()

    # Count remaining
    cursor = db.execute("SELECT COUNT(*) as count FROM memory")
    remaining = cursor.fetchone()["count"]

    return {
        "pruned": len(to_prune),
        "remaining": remaining,
        "pruned_names": to_prune,
    }


def stats() -> dict:
    """Get memory health statistics.

    Returns metrics about the learning system's health:
    - Total memories by type
    - Average effectiveness
    - Memories with feedback vs without
    - Embedding coverage
    """
    db = get_db()

    # Counts by type
    cursor = db.execute(
        """
        SELECT
            type,
            COUNT(*) as count,
            SUM(helped) as total_helped,
            SUM(failed) as total_failed,
            SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) as with_embedding
        FROM memory
        GROUP BY type
        """
    )

    by_type = {}
    total_count = 0
    total_helped = 0
    total_failed = 0
    total_with_embedding = 0

    for row in cursor:
        by_type[row["type"]] = {
            "count": row["count"],
            "total_helped": row["total_helped"] or 0,
            "total_failed": row["total_failed"] or 0,
            "with_embedding": row["with_embedding"],
        }
        total_count += row["count"]
        total_helped += row["total_helped"] or 0
        total_failed += row["total_failed"] or 0
        total_with_embedding += row["with_embedding"]

    # Calculate overall effectiveness
    total_uses = total_helped + total_failed
    overall_effectiveness = total_helped / total_uses if total_uses > 0 else 0.5

    # Count memories with feedback
    cursor = db.execute(
        "SELECT COUNT(*) as count FROM memory WHERE (helped + failed) > 0"
    )
    with_feedback = cursor.fetchone()["count"]

    return {
        "total": total_count,
        "by_type": by_type,
        "total_helped": total_helped,
        "total_failed": total_failed,
        "overall_effectiveness": round(overall_effectiveness, 3),
        "with_feedback": with_feedback,
        "without_feedback": total_count - with_feedback,
        "embedding_coverage": round(total_with_embedding / total_count, 3) if total_count > 0 else 0,
        "embeddings_available": embeddings_available(),
    }


def verify() -> dict:
    """Verify the learning loop is closed.

    Checks:
    1. Memories exist
    2. Some memories have feedback
    3. Embeddings are working
    4. No orphaned memories (very old, never used)

    Returns:
        {"status": "CLOSED"|"OPEN", "checks": dict, "issues": list}
    """
    s = stats()
    issues = []
    checks = {}

    # Check 1: Memories exist
    checks["memories_exist"] = s["total"] > 0
    if not checks["memories_exist"]:
        issues.append("No memories in database - run some tasks first")

    # Check 2: Some memories have feedback
    checks["has_feedback"] = s["with_feedback"] > 0
    if s["total"] > 0 and not checks["has_feedback"]:
        issues.append("No memories have feedback - ensure UTILIZED tracking is working")

    # Check 3: Embeddings are working
    checks["embeddings_available"] = s["embeddings_available"]
    if not checks["embeddings_available"]:
        issues.append("Embedding model not available - install sentence-transformers")

    # Check 4: Good embedding coverage
    checks["good_coverage"] = s["embedding_coverage"] >= 0.8 if s["total"] > 0 else True
    if s["total"] > 0 and not checks["good_coverage"]:
        issues.append(f"Low embedding coverage ({s['embedding_coverage']:.0%}) - some memories can't be found semantically")

    # Determine status
    critical_checks = ["memories_exist", "has_feedback"]
    status = "CLOSED" if all(checks.get(c, False) for c in critical_checks) else "OPEN"

    return {
        "status": status,
        "checks": checks,
        "issues": issues,
        "stats": s,
    }


def get_by_name(name: str) -> Optional[dict]:
    """Get a specific memory by name."""
    db = get_db()
    cursor = db.execute("SELECT * FROM memory WHERE name = ?", (name,))
    row = cursor.fetchone()
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


# ============================================================================
# CLI Interface
# ============================================================================

def _cli():
    """Command-line interface for memory operations."""
    import argparse

    parser = argparse.ArgumentParser(description="Loop memory operations")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # add
    add_p = subparsers.add_parser("add", help="Add a memory")
    add_p.add_argument("--trigger", required=True, help="When does this apply?")
    add_p.add_argument("--resolution", required=True, help="What do you do?")
    add_p.add_argument("--type", choices=["failure", "pattern"], default="failure")
    add_p.add_argument("--source", default="")
    add_p.add_argument("--name", default=None)

    # query
    query_p = subparsers.add_parser("query", help="Query memories")
    query_p.add_argument("text", help="Query text")
    query_p.add_argument("--type", choices=["failure", "pattern"], default=None)
    query_p.add_argument("--limit", type=int, default=5)

    # feedback
    fb_p = subparsers.add_parser("feedback", help="Record feedback")
    fb_p.add_argument("--utilized", required=True, help="JSON list of utilized memory names")
    fb_p.add_argument("--injected", required=True, help="JSON list of injected memory names")

    # prune
    prune_p = subparsers.add_parser("prune", help="Prune ineffective memories")
    prune_p.add_argument("--min-effectiveness", type=float, default=DEFAULT_PRUNE_THRESHOLD)
    prune_p.add_argument("--min-uses", type=int, default=3)

    # stats
    subparsers.add_parser("stats", help="Memory statistics")

    # verify
    subparsers.add_parser("verify", help="Verify learning loop")

    # get
    get_p = subparsers.add_parser("get", help="Get memory by name")
    get_p.add_argument("name", help="Memory name")

    args = parser.parse_args()

    if args.command == "add":
        result = add(
            trigger=args.trigger,
            resolution=args.resolution,
            memory_type=args.type,
            source=args.source,
            name=args.name,
        )
    elif args.command == "query":
        result = query(args.text, memory_type=args.type, limit=args.limit)
    elif args.command == "feedback":
        result = feedback(
            utilized=json.loads(args.utilized),
            injected=json.loads(args.injected),
        )
    elif args.command == "prune":
        result = prune(
            min_effectiveness=args.min_effectiveness,
            min_uses=args.min_uses,
        )
    elif args.command == "stats":
        result = stats()
    elif args.command == "verify":
        result = verify()
    elif args.command == "get":
        result = get_by_name(args.name)
        if result is None:
            result = {"error": f"Memory not found: {args.name}"}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
