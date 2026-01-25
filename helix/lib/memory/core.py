#!/usr/bin/env python3
"""Memory: the persistence layer for learning.

Core API (9 primitives):
- store(trigger, resolution, type, source) -> name
- recall(query, type, limit, expand) -> memories ranked by relevance x effectiveness x recency
- get(name) -> single memory
- edge(from_name, to_name, rel_type, weight) -> create/strengthen relationship
- edges(name, rel_type) -> query relationships
- feedback(names, delta) -> update scores (I decide the delta)
- decay(unused_days, min_uses) -> reduce scores on dormant memories
- prune(min_effectiveness, min_uses) -> remove low-performing memories
- health() -> system status

Scoring formula:
    score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
    effectiveness = helped / (helped + failed) if total > 0 else 0.5
    recency = 2^(-days_since_use / 7)
"""

import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Set

# Constants
DECAY_HALF_LIFE_DAYS = 7
DUPLICATE_THRESHOLD = 0.85
SCORE_WEIGHTS = {
    'relevance': 0.5,
    'effectiveness': 0.3,
    'recency': 0.2,
}
VALID_TYPES = ("failure", "pattern", "systemic")

# Support both module and script execution
try:
    from ..db.connection import get_db, write_lock
    from .embeddings import embed, to_blob, from_blob, cosine
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import embed, to_blob, from_blob, cosine


def _slug(text: str) -> str:
    """Create kebab-case slug."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] if len(s) > 50 else s


def _extract_file_patterns(trigger: str, resolution: str) -> List[str]:
    """Extract file path patterns from memory text."""
    text = f"{trigger} {resolution}"
    patterns = set()

    file_pattern = r'[\w\-./]+\.(py|js|ts|tsx|jsx|go|rs|java|rb|php|vue|svelte|md|json|yaml|yml|toml|sql|sh|css|scss|html)'
    for full_match in re.finditer(file_pattern, text, re.IGNORECASE):
        patterns.add(full_match.group(0))

    dir_pattern = r'(?:src|lib|app|components|utils|services|api|tests?|scripts?)/[\w\-/]+'
    for match in re.findall(dir_pattern, text):
        patterns.add(match)

    return list(patterns)


def _effectiveness(row) -> float:
    """Calculate effectiveness from helped/failed."""
    h, f = row["helped"] or 0, row["failed"] or 0
    return h / (h + f) if (h + f) > 0 else 0.5


def _recency_score(last_used: Optional[str], created_at: str) -> float:
    """Calculate recency score with exponential decay."""
    ref_date = last_used or created_at
    if not ref_date:
        return 0.5

    try:
        ref = datetime.fromisoformat(ref_date.replace("Z", "+00:00"))
        now = datetime.now()
        if ref.tzinfo:
            now = datetime.now(ref.tzinfo)
        days_ago = (now - ref).days
        return math.pow(2, -days_ago / DECAY_HALF_LIFE_DAYS)
    except:
        return 0.5


def _to_dict(row) -> dict:
    """Convert database row to memory dict."""
    return {
        "name": row["name"],
        "type": row["type"],
        "trigger": row["trigger"],
        "resolution": row["resolution"],
        "helped": row["helped"] or 0,
        "failed": row["failed"] or 0,
        "effectiveness": round(_effectiveness(row), 3),
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "source": row["source"]
    }


# =============================================================================
# CORE PRIMITIVES
# =============================================================================

def store(
    trigger: str,
    resolution: str,
    type: str = "failure",
    source: str = ""
) -> dict:
    """Store a memory. Returns {status, name, reason}.

    Types: failure, pattern, systemic
    Performs semantic deduplication - similar memories are merged.
    """
    if type not in VALID_TYPES:
        return {"status": "rejected", "name": "", "reason": f"type must be one of {VALID_TYPES}"}

    if len(trigger.strip()) < 10:
        return {"status": "rejected", "name": "", "reason": "trigger too short"}

    if not resolution.strip():
        return {"status": "rejected", "name": "", "reason": "resolution empty"}

    # Check for semantic duplicate
    new_emb = embed(trigger)
    if new_emb:
        db = get_db()
        for row in db.execute("SELECT name, embedding FROM memory WHERE type=? AND embedding IS NOT NULL", (type,)):
            if row["embedding"] and cosine(new_emb, from_blob(row["embedding"])) >= DUPLICATE_THRESHOLD:
                return {"status": "merged", "name": row["name"], "reason": "similar exists"}

    name = _slug(trigger)
    if not name:
        name = f"{type}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    emb_blob = None
    e = embed(trigger + " " + resolution)
    if e:
        emb_blob = to_blob(e)

    file_patterns = _extract_file_patterns(trigger, resolution)
    file_patterns_json = json.dumps(file_patterns) if file_patterns else None

    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source, file_patterns) VALUES (?,?,?,?,?,?,?,?)",
                (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source, file_patterns_json)
            )
            # Also insert into normalized file pattern table
            for pattern in file_patterns:
                db.execute(
                    "INSERT OR IGNORE INTO memory_file_pattern (memory_name, pattern) VALUES (?, ?)",
                    (name, pattern)
                )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    "INSERT INTO memory (name, type, trigger, resolution, embedding, created_at, source, file_patterns) VALUES (?,?,?,?,?,?,?,?)",
                    (name, type, trigger.strip(), resolution.strip(), emb_blob, now, source, file_patterns_json)
                )
                for pattern in file_patterns:
                    db.execute(
                        "INSERT OR IGNORE INTO memory_file_pattern (memory_name, pattern) VALUES (?, ?)",
                        (name, pattern)
                    )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def recall(
    query: str,
    type: Optional[str] = None,
    limit: int = 5,
    expand: bool = False,
    min_effectiveness: float = 0.0
) -> List[dict]:
    """Recall memories by semantic similarity.

    Args:
        query: Search query
        type: Filter by type (failure, pattern, systemic)
        limit: Maximum results
        expand: If True, include 1-hop graph neighbors
        min_effectiveness: Minimum effectiveness threshold

    Returns list with _relevance, _recency, _score fields.
    """
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
        # Fallback: by effectiveness only
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
        rec = _recency_score(r["last_used"], r["created_at"])

        score = (SCORE_WEIGHTS['relevance'] * rel) + \
                (SCORE_WEIGHTS['effectiveness'] * eff) + \
                (SCORE_WEIGHTS['recency'] * rec)

        m = _to_dict(r)
        m["_relevance"] = round(rel, 3)
        m["_recency"] = round(rec, 3)
        m["_score"] = round(score, 3)
        scored.append((score, rel, m))

    scored.sort(key=lambda x: -x[0])

    # Graph expansion if requested
    if expand and scored:
        seed_names = [m["name"] for _, _, m in scored[:limit * 2]]
        expanded_names = _expand_via_edges(seed_names, depth=1)

        # Fetch expanded memories not in seeds
        for name in expanded_names:
            if name not in seed_names:
                mem = get(name)
                if mem:
                    mem_emb = db.execute("SELECT embedding FROM memory WHERE name=?", (name,)).fetchone()
                    if mem_emb and mem_emb["embedding"]:
                        rel = cosine(q_emb, from_blob(mem_emb["embedding"]))
                    else:
                        rel = 0.3  # Default for graph-discovered memories
                    mem["_relevance"] = round(rel, 3)
                    mem["_recency"] = round(_recency_score(mem.get("last_used"), mem.get("created_at")), 3)

                    # Edge weight bonus: stronger edges boost score
                    edge_weight = _get_edge_weight_to_seeds(name, seed_names)
                    weight_bonus = min(edge_weight * 0.1, 0.2)  # Cap at 0.2 bonus

                    base_score = rel * 0.5 + mem["effectiveness"] * 0.3 + mem["_recency"] * 0.2
                    mem["_score"] = round(base_score + weight_bonus, 3)
                    mem["_via_edge"] = True
                    mem["_edge_weight"] = round(edge_weight, 2)
                    scored.append((mem["_score"], rel, mem))

        scored.sort(key=lambda x: -x[0])

    return [m for _, _, m in scored[:limit]]


def get(name: str) -> Optional[dict]:
    """Get specific memory by name."""
    db = get_db()
    row = db.execute("SELECT * FROM memory WHERE name=?", (name,)).fetchone()
    return _to_dict(row) if row else None


def similar_recent(
    trigger: str,
    threshold: float = 0.7,
    days: int = 7,
    type: Optional[str] = None
) -> List[dict]:
    """Find memories with similar triggers created in the last N days.

    Used for systemic detection: if len(result) >= 2 before storing a failure,
    the orchestrator should escalate to systemic type.

    Args:
        trigger: The trigger text to compare against
        threshold: Cosine similarity threshold (default 0.7)
        days: Look back window in days (default 7)
        type: Optional filter by memory type

    Returns:
        List of similar memories with _similarity score, sorted by similarity desc.
    """
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()

    # Build query
    sql = "SELECT * FROM memory WHERE embedding IS NOT NULL AND created_at >= ?"
    params = [cutoff]
    if type:
        sql += " AND type=?"
        params.append(type)

    rows = db.execute(sql, params).fetchall()
    if not rows:
        return []

    # Get embedding for trigger
    trigger_emb = embed(trigger)
    if trigger_emb is None:
        # Fallback: return recent memories without similarity scoring
        return [_to_dict(r) for r in rows[:10]]

    # Score by similarity
    results = []
    for r in rows:
        if not r["embedding"]:
            continue
        sim = cosine(trigger_emb, from_blob(r["embedding"]))
        if sim >= threshold:
            m = _to_dict(r)
            m["_similarity"] = round(sim, 3)
            results.append((sim, m))

    results.sort(key=lambda x: -x[0])
    return [m for _, m in results]


def edge(from_name: str, to_name: str, rel_type: str, weight: float = 1.0) -> dict:
    """Create or strengthen edge between memories.

    rel_type: solves, co_occurs, similar, causes
    If edge exists, weight is added to existing weight.
    """
    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        existing = db.execute(
            "SELECT weight FROM memory_edge WHERE from_name=? AND to_name=? AND rel_type=?",
            (from_name, to_name, rel_type)
        ).fetchone()

        if existing:
            new_weight = existing["weight"] + weight
            db.execute(
                "UPDATE memory_edge SET weight=? WHERE from_name=? AND to_name=? AND rel_type=?",
                (new_weight, from_name, to_name, rel_type)
            )
        else:
            db.execute(
                "INSERT INTO memory_edge (from_name, to_name, rel_type, weight, created_at) VALUES (?,?,?,?,?)",
                (from_name, to_name, rel_type, weight, now)
            )
        db.commit()

    return {"from": from_name, "to": to_name, "rel_type": rel_type, "weight": weight}


def edges(name: Optional[str] = None, rel_type: Optional[str] = None) -> List[dict]:
    """Query edges from/to a memory.

    Args:
        name: Filter by from_name or to_name
        rel_type: Filter by relationship type
    """
    db = get_db()
    query = "SELECT * FROM memory_edge WHERE 1=1"
    params = []

    if name:
        query += " AND (from_name=? OR to_name=?)"
        params.extend([name, name])
    if rel_type:
        query += " AND rel_type=?"
        params.append(rel_type)

    rows = db.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def suggest_edges(memory_name: str, limit: int = 5) -> List[dict]:
    """Suggest edge connections for a memory based on semantic similarity.

    After storing a new memory, call this to surface potential edges.
    The orchestrator reviews suggestions and creates edges with judgment.

    Args:
        memory_name: Name of the memory to find edge candidates for
        limit: Maximum suggestions to return

    Returns:
        List of suggestions: [{from, to, rel_type, reason, confidence}]
        - 'solves': pattern that might solve a failure
        - 'co_occurs': memories with similar context (same files/framework)
        - 'similar': semantically similar memories
    """
    db = get_db()

    # Get the source memory
    source = db.execute("SELECT * FROM memory WHERE name=?", (memory_name,)).fetchone()
    if not source:
        return []

    source_emb = from_blob(source["embedding"]) if source["embedding"] else None
    source_type = source["type"]
    source_trigger = source["trigger"]

    suggestions = []
    seen_pairs = set()

    # Get existing edges to avoid suggesting duplicates
    existing = {(e["from_name"], e["to_name"], e["rel_type"]) for e in edges(name=memory_name)}

    # 1. Find semantically similar memories
    if source_emb:
        for row in db.execute("SELECT * FROM memory WHERE name != ? AND embedding IS NOT NULL", (memory_name,)):
            other_emb = from_blob(row["embedding"])
            sim = cosine(source_emb, other_emb)

            if sim >= 0.6:  # Lower threshold for suggestions
                pair_key = tuple(sorted([memory_name, row["name"]]))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                # Determine rel_type based on memory types
                if source_type == "pattern" and row["type"] == "failure":
                    rel_type = "solves"
                    direction = (memory_name, row["name"])
                    reason = f"Pattern may solve failure (similarity: {sim:.2f})"
                elif source_type == "failure" and row["type"] == "pattern":
                    rel_type = "solves"
                    direction = (row["name"], memory_name)
                    reason = f"Pattern may solve this failure (similarity: {sim:.2f})"
                elif source_type == row["type"]:
                    rel_type = "similar"
                    direction = (memory_name, row["name"])
                    reason = f"Similar {source_type}s (similarity: {sim:.2f})"
                else:
                    rel_type = "co_occurs"
                    direction = (memory_name, row["name"])
                    reason = f"Related memories (similarity: {sim:.2f})"

                # Skip if edge already exists
                if (*direction, rel_type) in existing:
                    continue

                suggestions.append({
                    "from": direction[0],
                    "to": direction[1],
                    "rel_type": rel_type,
                    "reason": reason,
                    "confidence": round(sim, 3)
                })

    # Sort by confidence and limit
    suggestions.sort(key=lambda x: -x["confidence"])
    return suggestions[:limit]


def _expand_via_edges(names: List[str], depth: int = 1) -> Set[str]:
    """Get names reachable within depth hops."""
    current = set(names)
    for _ in range(depth):
        new_names = set()
        for name in current:
            for e in edges(name=name):
                new_names.add(e["from_name"])
                new_names.add(e["to_name"])
        current.update(new_names)
    return current


def _get_edge_weight_to_seeds(name: str, seed_names: List[str]) -> float:
    """Get total edge weight connecting a memory to seed memories.

    Used to boost scores of graph-expanded memories based on edge strength.
    """
    db = get_db()
    total = 0.0
    for seed in seed_names:
        row = db.execute(
            "SELECT weight FROM memory_edge WHERE (from_name=? AND to_name=?) OR (from_name=? AND to_name=?)",
            (name, seed, seed, name)
        ).fetchone()
        if row:
            total += row["weight"]
    return total


def feedback(names: List[str], delta: float) -> dict:
    """Update scores. I decide the delta.

    Args:
        names: Memory names to update
        delta: Positive for helped, negative for failed

    Returns count of updated memories.
    """
    db = get_db()
    now = datetime.now().isoformat()
    updated = 0

    with write_lock():
        for name in set(names):  # Dedupe
            row = db.execute("SELECT id FROM memory WHERE name=?", (name,)).fetchone()
            if not row:
                continue

            if delta > 0:
                db.execute(
                    "UPDATE memory SET helped = helped + ?, last_used = ? WHERE name = ?",
                    (delta, now, name)
                )
            else:
                db.execute(
                    "UPDATE memory SET failed = failed + ?, last_used = ? WHERE name = ?",
                    (abs(delta), now, name)
                )
            updated += 1
        db.commit()

    return {"updated": updated, "delta": delta, "names": list(set(names))}


def decay(unused_days: int = 30, min_uses: int = 2) -> dict:
    """Decay dormant memories by halving their scores.

    Affects memories that:
    - Haven't been used in unused_days
    - Have fewer than min_uses total uses

    Returns count of affected memories.
    """
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=unused_days)).isoformat()

    with write_lock():
        cursor = db.execute("""
            UPDATE memory
            SET helped = helped * 0.5, failed = failed * 0.5
            WHERE (last_used IS NULL OR last_used < ?)
            AND (helped + failed) < ?
        """, (cutoff, min_uses))
        db.commit()
        affected = cursor.rowcount

    return {"decayed": affected, "threshold_days": unused_days, "min_uses": min_uses}


def decay_edges(unused_days: int = 60) -> dict:
    """Decay edge weights for unused relationships.

    Edges whose connected memories haven't been used recently
    have their weights halved. This prevents stale relationships
    from dominating graph expansion.

    Args:
        unused_days: Days of inactivity before decay

    Returns:
        Count of affected edges
    """
    db = get_db()
    cutoff = (datetime.now() - timedelta(days=unused_days)).isoformat()

    with write_lock():
        # Find edges where BOTH connected memories are dormant
        cursor = db.execute("""
            UPDATE memory_edge
            SET weight = weight * 0.5
            WHERE from_name IN (
                SELECT name FROM memory WHERE last_used IS NULL OR last_used < ?
            )
            AND to_name IN (
                SELECT name FROM memory WHERE last_used IS NULL OR last_used < ?
            )
        """, (cutoff, cutoff))
        db.commit()
        affected = cursor.rowcount

    return {"edges_decayed": affected, "threshold_days": unused_days}


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
            db.execute("DELETE FROM memory_edge WHERE from_name=? OR to_name=?", (n, n))
            db.execute("DELETE FROM memory_file_pattern WHERE memory_name=?", (n,))
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    return {"pruned": len(to_remove), "remaining": remaining, "removed": to_remove}


def consolidate(similarity_threshold: float = 0.9) -> dict:
    """Merge highly similar memories to prevent bloat."""
    db = get_db()
    rows = db.execute("SELECT * FROM memory WHERE embedding IS NOT NULL").fetchall()

    merged_count = 0
    seen = set()

    for i, r1 in enumerate(rows):
        if r1["name"] in seen:
            continue
        emb1 = from_blob(r1["embedding"])

        for r2 in rows[i+1:]:
            if r2["name"] in seen:
                continue
            if r1["type"] != r2["type"]:
                continue

            emb2 = from_blob(r2["embedding"])
            sim = cosine(emb1, emb2)

            if sim >= similarity_threshold:
                h1, f1 = r1["helped"] or 0, r1["failed"] or 0
                h2, f2 = r2["helped"] or 0, r2["failed"] or 0

                if (h1 + f1) >= (h2 + f2):
                    keep, remove = r1, r2
                else:
                    keep, remove = r2, r1

                with write_lock():
                    db.execute(
                        "UPDATE memory SET helped=helped+?, failed=failed+? WHERE name=?",
                        (remove["helped"] or 0, remove["failed"] or 0, keep["name"])
                    )
                    db.execute("DELETE FROM memory WHERE name=?", (remove["name"],))
                    db.execute("DELETE FROM memory_file_pattern WHERE memory_name=?", (remove["name"],))
                    # Redirect edges
                    db.execute(
                        "UPDATE memory_edge SET from_name=? WHERE from_name=?",
                        (keep["name"], remove["name"])
                    )
                    db.execute(
                        "UPDATE memory_edge SET to_name=? WHERE to_name=?",
                        (keep["name"], remove["name"])
                    )
                    db.commit()

                seen.add(remove["name"])
                merged_count += 1

    return {"merged": merged_count, "remaining": len(rows) - merged_count}


def health() -> dict:
    """Check learning system health."""
    db = get_db()

    total = db.execute("SELECT COUNT(*) as c FROM memory").fetchone()["c"]
    by_type = {}
    for row in db.execute("SELECT type, COUNT(*) as c, SUM(helped) as h, SUM(failed) as f FROM memory GROUP BY type"):
        by_type[row["type"]] = {"count": row["c"], "helped": row["h"] or 0, "failed": row["f"] or 0}

    with_feedback = db.execute("SELECT COUNT(*) as c FROM memory WHERE (helped+failed)>0").fetchone()["c"]
    edge_count = db.execute("SELECT COUNT(*) as c FROM memory_edge").fetchone()["c"]

    # Edge type breakdown
    edge_types = {}
    for row in db.execute("SELECT rel_type, COUNT(*) as c FROM memory_edge GROUP BY rel_type"):
        edge_types[row["rel_type"]] = row["c"]

    total_h = sum(t["helped"] for t in by_type.values())
    total_f = sum(t["failed"] for t in by_type.values())
    effectiveness = total_h / (total_h + total_f) if (total_h + total_f) > 0 else 0.5

    loop_closed = total > 0 and with_feedback > 0
    issues = []
    if total == 0:
        issues.append("No memories yet")
    elif with_feedback == 0:
        issues.append("No feedback recorded - learning loop not closed")

    return {
        "status": "HEALTHY" if loop_closed and not issues else "NEEDS_ATTENTION",
        "total_memories": total,
        "total_edges": edge_count,
        "by_type": by_type,
        "edge_types": edge_types,
        "effectiveness": round(effectiveness, 3),
        "with_feedback": with_feedback,
        "issues": issues
    }


# =============================================================================
# LEGACY COMPATIBILITY
# =============================================================================

def recall_by_file_patterns(delta_files: List[str], limit: int = 3) -> List[dict]:
    """Query memories by file path patterns using normalized table."""
    db = get_db()
    matches = []
    seen_names = set()

    for delta_file in delta_files:
        try:
            parts = Path(delta_file).parts
            filename = Path(delta_file).name
            stem = Path(delta_file).stem
            partial_path = "/".join(parts[-2:]) if len(parts) >= 2 else filename
        except Exception:
            filename = delta_file.split("/")[-1] if "/" in delta_file else delta_file
            stem = filename.rsplit(".", 1)[0] if "." in filename else filename
            partial_path = delta_file

        # Query normalized pattern table first
        rows = db.execute("""
            SELECT DISTINCT m.* FROM memory m
            JOIN memory_file_pattern p ON m.name = p.memory_name
            WHERE p.pattern LIKE ? OR p.pattern LIKE ? OR p.pattern LIKE ?
            ORDER BY (m.helped * 1.0 / (m.helped + m.failed + 1)) DESC
            LIMIT ?
        """, (f'%{filename}%', f'%{stem}%', f'%{partial_path}%', limit * 2)).fetchall()

        # Fallback to JSON column if no results
        if not rows:
            rows = db.execute("""
                SELECT * FROM memory
                WHERE file_patterns IS NOT NULL
                  AND (file_patterns LIKE ? OR file_patterns LIKE ? OR file_patterns LIKE ?)
                ORDER BY (helped * 1.0 / (helped + failed + 1)) DESC
                LIMIT ?
            """, (f'%{filename}%', f'%{stem}%', f'%{partial_path}%', limit * 2)).fetchall()

        for row in rows:
            name = row["name"]
            if name not in seen_names:
                seen_names.add(name)
                matches.append(_to_dict(row))

    matches.sort(key=lambda m: m.get("effectiveness", 0.5), reverse=True)
    return matches[:limit]


def feedback_from_verification(task_id: str, verify_passed: bool, injected: List[str], task_objective: str = "") -> dict:
    """DEPRECATED: Use feedback() with explicit delta instead.

    This function uses fixed ±0.5 delta which undermines the orchestrator's
    judgment-based feedback mechanism. The orchestrator should decide delta
    based on memory relevance to the outcome:

        | Situation                        | Delta |
        |----------------------------------|-------|
        | Success, memory was relevant     | +0.7  |
        | Success, memory was tangential   | +0.3  |
        | Failure, memory may have misled  | -0.5  |
        | Failure, memory was irrelevant   | -0.2  |

    Prefer: feedback(names=['mem1', 'mem2'], delta=0.7)
    """
    import warnings
    warnings.warn(
        "feedback_from_verification() is deprecated. Use feedback(names, delta) with explicit delta.",
        DeprecationWarning,
        stacklevel=2
    )
    delta = 0.5 if verify_passed else -0.5
    result = feedback(injected, delta)
    # Map to legacy response format
    return {
        "credited": result["updated"] if verify_passed else 0,
        "task_id": task_id,
        "verify_passed": verify_passed,
        "injected_count": len(injected)
    }


def chunk(task_objective: str, outcome: str, approach: str, source: str = "chunked") -> dict:
    """Extract a reusable rule from a successful task completion (SOAR pattern)."""
    if not outcome.lower().startswith("success"):
        return {"status": "skipped", "reason": "only chunk successful outcomes"}

    trigger = f"Task: {task_objective}"
    resolution = f"Approach that worked: {approach}"

    existing = recall(trigger, type="pattern", limit=3)
    for m in existing:
        if m.get("_relevance", 0) > DUPLICATE_THRESHOLD:
            db = get_db()
            with write_lock():
                db.execute(
                    "UPDATE memory SET helped=helped+1, last_used=? WHERE name=?",
                    (datetime.now().isoformat(), m["name"])
                )
                db.commit()
            return {"status": "strengthened", "name": m["name"], "reason": "similar pattern exists, reinforced it"}

    return store(trigger=trigger, resolution=resolution, type="pattern", source=source)


# =============================================================================
# CLI
# =============================================================================

def _log_verbose(cmd: str, args: dict, result: dict) -> None:
    """Print structured log to stderr when --verbose is enabled."""
    import sys
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "command": cmd,
        "args": args,
        "result_type": type(result).__name__,
        "result_size": len(result) if isinstance(result, (list, dict)) else 1
    }
    print(json.dumps(log_entry), file=sys.stderr)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="Helix memory operations")
    p.add_argument("--verbose", "-v", action="store_true", help="Print structured log to stderr")
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
    s.add_argument("--expand", action="store_true", help="Include 1-hop graph neighbors")

    s = sub.add_parser("similar-recent", help="Find similar memories for systemic detection")
    s.add_argument("trigger", help="Trigger text to compare against")
    s.add_argument("--threshold", type=float, default=0.7, help="Cosine similarity threshold")
    s.add_argument("--days", type=int, default=7, help="Look back window in days")
    s.add_argument("--type", default=None, help="Filter by memory type")

    s = sub.add_parser("get")
    s.add_argument("name")

    s = sub.add_parser("edge")
    s.add_argument("--from", dest="from_name", required=True)
    s.add_argument("--to", dest="to_name", required=True)
    s.add_argument("--rel", required=True, help="solves|co_occurs|similar|causes")
    s.add_argument("--weight", type=float, default=1.0)

    s = sub.add_parser("edges")
    s.add_argument("--name", default=None)
    s.add_argument("--rel", default=None)

    s = sub.add_parser("suggest-edges", help="Suggest edge connections for a memory")
    s.add_argument("memory_name", help="Name of the memory to find edge candidates for")
    s.add_argument("--limit", type=int, default=5, help="Maximum suggestions to return")

    s = sub.add_parser("feedback")
    s.add_argument("--names", required=True, help="JSON list of memory names")
    s.add_argument("--delta", type=float, required=True, help="Positive for helped, negative for failed")

    # Legacy feedback-verify for backwards compatibility
    s = sub.add_parser("feedback-verify")
    s.add_argument("--task-id", required=True)
    s.add_argument("--verify-passed", type=lambda x: x.lower() == "true", required=True)
    s.add_argument("--injected", required=True)

    s = sub.add_parser("decay")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--min-uses", type=int, default=2)

    s = sub.add_parser("decay-edges")
    s.add_argument("--days", type=int, default=60, help="Decay edges for memories unused this many days")

    s = sub.add_parser("prune")
    s.add_argument("--threshold", type=float, default=0.25, dest="min_effectiveness")
    s.add_argument("--min-uses", type=int, default=3)

    sub.add_parser("consolidate")
    sub.add_parser("health")

    s = sub.add_parser("chunk")
    s.add_argument("--task", required=True)
    s.add_argument("--outcome", required=True)
    s.add_argument("--approach", required=True)
    s.add_argument("--source", default="chunked")

    args = p.parse_args()
    r = None

    if args.cmd == "store":
        r = store(args.trigger, args.resolution, args.type, args.source)
    elif args.cmd == "recall":
        r = recall(args.query, args.type, args.limit, expand=args.expand)
    elif args.cmd == "similar-recent":
        r = similar_recent(args.trigger, args.threshold, args.days, args.type)
    elif args.cmd == "get":
        r = get(args.name)
        if r is None:
            r = {"error": "not found"}
    elif args.cmd == "edge":
        r = edge(args.from_name, args.to_name, args.rel, args.weight)
    elif args.cmd == "edges":
        r = edges(args.name, args.rel)
    elif args.cmd == "suggest-edges":
        r = suggest_edges(args.memory_name, args.limit)
    elif args.cmd == "feedback":
        r = feedback(json.loads(args.names), args.delta)
    elif args.cmd == "feedback-verify":
        r = feedback_from_verification(
            task_id=args.task_id,
            verify_passed=args.verify_passed,
            injected=json.loads(args.injected)
        )
    elif args.cmd == "decay":
        r = decay(args.days, args.min_uses)
    elif args.cmd == "decay-edges":
        r = decay_edges(args.days)
    elif args.cmd == "prune":
        r = prune(min_effectiveness=args.min_effectiveness, min_uses=args.min_uses)
    elif args.cmd == "health":
        r = health()
    elif args.cmd == "consolidate":
        r = consolidate()
    elif args.cmd == "chunk":
        r = chunk(args.task, args.outcome, args.approach, args.source)

    # Verbose logging
    if args.verbose and r is not None:
        cmd_args = {k: v for k, v in vars(args).items() if k not in ('cmd', 'verbose')}
        _log_verbose(args.cmd, cmd_args, r)

    print(json.dumps(r, indent=2))
