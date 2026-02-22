"""Graph edges between insights.

Manages relationship edges (similar, led_to) in the insight_edges table.
Used by store() for auto-linking, extract_learning for provenance, prune() for cleanup.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

try:
    from ..db.connection import get_db, write_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock


def _utcnow() -> datetime:
    """Return current UTC time as naive datetime."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def add_edges(edges: List[Tuple[int, int, float, str]]) -> int:
    """Insert edges into insight_edges.

    Each tuple: (src_id, dst_id, weight, relation).
    For 'similar' relation, enforces canonical order (min, max) so
    (A,B) and (B,A) map to the same row.
    Uses INSERT OR IGNORE to skip existing edges.

    Returns count of inserted edges.
    """
    if not edges:
        return 0

    db = get_db()
    now = _utcnow().isoformat()

    rows_to_insert = []
    for src_id, dst_id, weight, relation in edges:
        if src_id == dst_id:
            continue  # no self-loops
        # Canonical ordering for undirected relations
        if relation == "similar":
            a, b = min(src_id, dst_id), max(src_id, dst_id)
        else:
            a, b = src_id, dst_id
        rows_to_insert.append((a, b, weight, relation, now))

    if not rows_to_insert:
        return 0

    with write_lock():
        db.executemany(
            "INSERT OR IGNORE INTO insight_edges (src_id, dst_id, weight, relation, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            rows_to_insert
        )
        db.commit()

    return len(rows_to_insert)


def get_neighbors(insight_ids: List[int], relation: Optional[str] = None,
                  limit: int = 10) -> list:
    """Fetch graph-adjacent insight rows with edge metadata.

    Returns full insight rows enriched with edge_weight and edge_relation.
    Single JOIN query — no second roundtrip.

    Args:
        insight_ids: Source insight IDs to find neighbors for
        relation: Optional filter by relation type ('similar', 'led_to')
        limit: Maximum neighbors to return
    """
    if not insight_ids:
        return []

    db = get_db()
    placeholders = ",".join("?" for _ in insight_ids)

    # Bidirectional lookup: match src or dst
    params = list(insight_ids) + list(insight_ids)
    relation_clause = ""
    if relation:
        relation_clause = "AND e.relation = ?"
        params.append(relation)
    params.append(limit)

    query = f"""
        SELECT i.*, e.weight AS edge_weight, e.relation AS edge_relation
        FROM insight_edges e
        JOIN insight i ON i.id = CASE
            WHEN e.src_id IN ({placeholders}) THEN e.dst_id
            ELSE e.src_id
        END
        WHERE (e.src_id IN ({placeholders}) OR e.dst_id IN ({placeholders}))
        {relation_clause}
        AND i.id NOT IN ({placeholders})
        ORDER BY e.weight DESC
        LIMIT ?
    """
    # Need insight_ids 4 times: CASE src_id IN, WHERE src_id IN, WHERE dst_id IN, NOT IN
    params = list(insight_ids) + list(insight_ids) + list(insight_ids)
    if relation:
        params.append(relation)
    params += list(insight_ids)
    params.append(limit)

    rows = db.execute(query, params).fetchall()
    return rows


def delete_edges_for(insight_ids: List[int]) -> int:
    """Delete all edges referencing any of the given insight IDs.

    Called by prune() for manual CASCADE (FK pragma not enabled).
    Deletes edges where src_id OR dst_id is in the given set.

    Returns count of deleted edges.
    """
    if not insight_ids:
        return 0

    db = get_db()
    placeholders = ",".join("?" for _ in insight_ids)

    with write_lock():
        cursor = db.execute(
            f"DELETE FROM insight_edges WHERE src_id IN ({placeholders}) OR dst_id IN ({placeholders})",
            list(insight_ids) + list(insight_ids)
        )
        db.commit()
        return cursor.rowcount
