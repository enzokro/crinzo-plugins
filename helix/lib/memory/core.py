#!/usr/bin/env python3
"""Memory: unified insight storage and retrieval.

Core API (8 primitives):
- store(content, tags) -> {"status": "added"|"merged", "name": str}
- recall(query, limit, suppress_names) -> insights sorted by relevance * (0.5 + 0.5 * causal_eff)
- feedback(names, outcome, causal_names) -> update effectiveness with causal filtering
- decay(unused_days) -> decay dormant insights
- prune(min_effectiveness, min_uses) -> remove low-performing insights
- count() -> total insight count (lightweight)
- health() -> system status

Scoring formula (multiplicative):
    score = relevance * (0.5 + 0.5 * effectiveness)
    eff=1.0 (proven): score = relevance * 1.0
    eff=0.5 (neutral): score = relevance * 0.75
    eff=0.0 (bad): score = relevance * 0.5
Feedback EMA weight: 0.2 (~3 positive outcomes to move 0.5 → 0.6)
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

# Scoring: multiplicative — effectiveness modulates relevance, not competes with it
# score = relevance * (0.5 + 0.5 * effectiveness)
DUPLICATE_THRESHOLD = 0.85
MIN_RELEVANCE_DEFAULT = 0.35  # arctic-embed-m-v1.5: unrelated 0.05-0.25, related 0.35+
CAUSAL_SIMILARITY_THRESHOLD = 0.50  # For feedback attribution filtering (tighter than 0.40)

# Graph: auto-linking and expansion
RELATED_THRESHOLD = 0.60    # Semantic similarity floor for auto-linking (below DUPLICATE_THRESHOLD)
MAX_AUTOLINK_EDGES = 5      # Cap edges per new insight
HOP_DISCOUNT = 0.7          # Score multiplier for graph-adjacent insights (PageRank-informed)

# Tuning parameters — extracted from inline for visibility
FEEDBACK_EMA_WEIGHT = 0.2       # Learning rate for causal feedback (was 0.1; ~3 outcomes to move 0.5→0.6)
DECAY_RATE = 0.1                # Rate dormant insights drift toward neutral per session_end
EROSION_RATE = 0.09             # Rate non-causal insights drift toward neutral (loss-aversion calibrated: EMA/2.25)
CAUSAL_ADJUSTMENT_FLOOR = 0.33  # Minimum multiplier for causal hit ratio (at-chance for 3-use minimum)
CAUSAL_MIN_USES = 3             # Uses before causal adjustment kicks in
RECENCY_DECAY_PER_DAY = 0.003  # 0.3% score penalty per day unused (231d half-life)
RECENCY_FLOOR = 0.85            # Maximum 15% recency penalty; floor reached at ~50 days
RRF_K = 60                      # Reciprocal Rank Fusion smoothing constant

# Support both module and script execution
try:
    from ..db.connection import get_db, write_lock
    from .embeddings import embed, to_blob, build_embedding_matrix
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import embed, to_blob, build_embedding_matrix


def _utcnow() -> datetime:
    """Return current UTC time as naive datetime (no tzinfo).

    Matches SQLite datetime('now') format for consistent comparisons.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slug(text: str) -> str:
    """Create kebab-case slug from text."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] if len(s) > 50 else s


def _effectiveness(row) -> float:
    """Get effectiveness from row (already stored as 0-1)."""
    return row["effectiveness"] if row["effectiveness"] is not None else 0.5


def _causal_adjusted_effectiveness(row) -> float:
    """Adjust effectiveness by causal hit ratio at read time.

    Insights with high use_count but low causal_hits are penalized.
    Floor adjustment multiplier at 0.3 (max 70% penalty).
    Skip adjustment for insights with < 3 uses (insufficient data).
    """
    eff = _effectiveness(row)
    use_count = row["use_count"] or 0
    if use_count < CAUSAL_MIN_USES:
        return eff

    causal_hits = row["causal_hits"] or 0
    causal_ratio = causal_hits / use_count
    adjustment = max(CAUSAL_ADJUSTMENT_FLOOR, causal_ratio)
    return eff * adjustment


def _to_dict(row) -> dict:
    """Convert database row to insight dict (hot path — skips tag parsing)."""
    return {
        "name": row["name"],
        "content": row["content"],
        "effectiveness": round(_effectiveness(row), 3),
        "use_count": row["use_count"] or 0,
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "tags": [],
        "causal_hits": row["causal_hits"] or 0,
    }


def _to_dict_full(row) -> dict:
    """Convert database row to insight dict with full tag parsing."""
    d = _to_dict(row)
    if row["tags"]:
        try:
            d["tags"] = json.loads(row["tags"])
        except Exception:
            pass
    return d


# =============================================================================
# FTS5 HELPERS
# =============================================================================

# FTS5 reserved words that must be stripped from user queries
_FTS5_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR"})


def _build_fts_query(query: str) -> str:
    """Sanitize natural-language query into FTS5 MATCH expression.

    Splits on whitespace, strips non-alphanumeric chars (keeps hyphens),
    removes FTS5 reserved words, wraps tokens in double quotes for literal
    matching, joins with OR.

    Returns empty string if no valid tokens remain.
    """
    tokens = []
    for word in query.split():
        # Strip non-alphanumeric except hyphens (for terms like ECONNREFUSED)
        cleaned = re.sub(r"[^a-zA-Z0-9\-]", "", word)
        if not cleaned:
            continue
        if cleaned.upper() in _FTS5_RESERVED:
            continue
        tokens.append(f'"{cleaned}"')
    return " OR ".join(tokens)


def _fts_search(db, query: str, limit: int, suppress_set: set) -> list:
    """Run FTS5 keyword search, returning (rowid, rank_position) tuples.

    Gracefully returns [] on empty query, FTS5 error, or missing table.
    """
    fts_expr = _build_fts_query(query)
    if not fts_expr:
        return []

    try:
        rows = db.execute(
            "SELECT rowid, rank FROM insight_fts WHERE insight_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_expr, limit)
        ).fetchall()
    except Exception:
        return []

    return rows


# =============================================================================
# CORE PRIMITIVES
# =============================================================================

def store(content: str, tags: list = None, initial_effectiveness: float = 0.5) -> dict:
    """Store an insight.

    Args:
        content: "When X, do Y because Z" format
        tags: Optional list of tags
        initial_effectiveness: Starting effectiveness (default 0.5 neutral).
                              Derived insights use lower values.

    Returns: {"status": "added"|"merged", "name": str, "reason": str}
    """
    if not content or len(content.strip()) < 20:
        return {"status": "rejected", "name": "", "reason": "content too short (min 20 chars)"}

    content = content.strip()
    tags = tags or []

    # Check for semantic duplicate (vectorized)
    new_emb = embed(content, is_query=False)
    dedup_rows = None  # Retain for auto-linking after insert
    dedup_sims = None
    if new_emb:
        db = get_db()
        dedup_rows = db.execute("SELECT id, name, embedding FROM insight WHERE embedding IS NOT NULL").fetchall()
        if dedup_rows:
            import numpy as np
            q_vec = np.array(new_emb, dtype=np.float32)
            names = [r["name"] for r in dedup_rows]
            mat = build_embedding_matrix(r["embedding"] for r in dedup_rows)
            dedup_sims = mat @ q_vec
            best_idx = int(np.argmax(dedup_sims))
            if dedup_sims[best_idx] >= DUPLICATE_THRESHOLD:
                match_name = names[best_idx]
                now = _utcnow().isoformat()
                with write_lock():
                    # Check if new content should replace existing (better articulation)
                    existing = db.execute(
                        "SELECT content, effectiveness FROM insight WHERE name = ?",
                        (match_name,)
                    ).fetchone()
                    if existing and (
                        len(content) > len(existing["content"])
                        or (existing["effectiveness"] or 0.5) < 0.5
                    ):
                        tags_json = json.dumps(tags)
                        db.execute(
                            "UPDATE insight SET content=?, embedding=?, tags=?, last_used=? WHERE name=?",
                            (content, to_blob(new_emb), tags_json, now, match_name)
                        )
                    else:
                        db.execute(
                            "UPDATE insight SET last_used=? WHERE name=?",
                            (now, match_name)
                        )
                    db.commit()
                return {"status": "merged", "name": match_name, "reason": "similar exists"}

    name = _slug(content[:50])
    if not name:
        name = f"insight-{_utcnow().strftime('%Y%m%d%H%M%S')}"

    emb_blob = to_blob(new_emb) if new_emb else None
    tags_json = json.dumps(tags)

    db = get_db()
    now = _utcnow().isoformat()

    with write_lock():
        try:
            cursor = db.execute(
                "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                (name, content, emb_blob, initial_effectiveness, 0, now, tags_json)
            )
            new_id = cursor.lastrowid
            db.commit()
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{_utcnow().strftime('%H%M%S')}"
                cursor = db.execute(
                    "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                    (name, content, emb_blob, initial_effectiveness, 0, now, tags_json)
                )
                new_id = cursor.lastrowid
                db.commit()
            else:
                raise

    # Auto-link to semantically related insights (reuses dedup similarity vector)
    if new_id and dedup_rows and dedup_sims is not None:
        try:
            from .edges import add_edges
        except ImportError:
            from edges import add_edges
        try:
            import numpy as np
            # Find candidates: RELATED_THRESHOLD <= sim < DUPLICATE_THRESHOLD
            candidates = []
            for i, sim in enumerate(dedup_sims):
                s = float(sim)
                if RELATED_THRESHOLD <= s < DUPLICATE_THRESHOLD:
                    candidates.append((dedup_rows[i]["id"], s))
            # Top-K by similarity
            candidates.sort(key=lambda x: -x[1])
            edges_to_add = [
                (new_id, cid, weight, "similar")
                for cid, weight in candidates[:MAX_AUTOLINK_EDGES]
            ]
            if edges_to_add:
                add_edges(edges_to_add)
        except Exception:
            pass  # auto-linking is best-effort

    return {"status": "added", "name": name, "reason": ""}


def recall(query: str, limit: int = 5, min_effectiveness: float = 0.0,
           min_relevance: float = MIN_RELEVANCE_DEFAULT,
           suppress_names: List[str] = None,
           graph_hops: int = 0) -> List[dict]:
    """Recall insights by hybrid vector + keyword search with RRF fusion.

    Args:
        query: Search query
        limit: Maximum results
        min_effectiveness: Minimum effectiveness threshold
        min_relevance: Minimum cosine similarity (0.35 default). "No memory" beats "wrong memory."
        graph_hops: Expand results via graph neighbors (0=off, 1=1-hop). Default off.

    Scoring: rrf_score * (0.5 + 0.5 * eff) * recency
    RRF fuses vector similarity ranking with FTS5 keyword ranking.
    Degrades gracefully to pure vector when FTS5 is unavailable.

    Returns list with _relevance, _score, _hop fields.
    """
    db = get_db()

    q_emb = embed(query, is_query=True)
    if q_emb is None:
        # Fallback: by effectiveness only
        rows = db.execute(
            "SELECT * FROM insight ORDER BY effectiveness DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [_to_dict(r) for r in rows]

    # Single-pass: fetch all columns, score, return top-N
    # SQL-side effectiveness filter avoids transferring rows we'd discard
    rows = db.execute(
        "SELECT * FROM insight WHERE embedding IS NOT NULL AND effectiveness >= ?",
        (min_effectiveness,)
    ).fetchall()
    if not rows:
        return []

    suppress_set = set(suppress_names) if suppress_names else set()

    # Pre-filter by suppress list (cheap check before matrix ops)
    candidates = []
    for r in rows:
        if suppress_set and r["name"] in suppress_set:
            continue
        candidates.append(r)

    if not candidates:
        return []

    # Vectorized cosine: single matrix multiply for all candidates
    import numpy as np
    q_vec = np.array(q_emb, dtype=np.float32)
    mat = build_embedding_matrix(r["embedding"] for r in candidates)
    similarities = mat @ q_vec

    # --- Vector ranking ---
    # Build (index, cosine_sim) sorted descending, filtered by min_relevance
    vector_ranked = sorted(
        ((i, float(similarities[i])) for i in range(len(candidates))),
        key=lambda x: -x[1]
    )
    vector_ranked = [(i, sim) for i, sim in vector_ranked if sim >= min_relevance]

    # Map candidate index → (vector_rank_position_1indexed, cosine_sim)
    vec_rank_map = {}
    for rank_pos, (idx, sim) in enumerate(vector_ranked, 1):
        vec_rank_map[idx] = (rank_pos, sim)

    # --- FTS5 keyword ranking ---
    fts_rows = _fts_search(db, query, limit * 3, suppress_set)

    # Map candidate index → fts_rank_position (1-indexed)
    # FTS returns rowids; match against candidate row IDs
    candidate_id_to_idx = {r["id"]: i for i, r in enumerate(candidates)}
    fts_rank_map = {}
    fts_pos = 0
    for fts_row in fts_rows:
        rowid = fts_row["rowid"] if isinstance(fts_row, dict) or hasattr(fts_row, "keys") else fts_row[0]
        idx = candidate_id_to_idx.get(rowid)
        if idx is None:
            continue  # FTS hit not in candidate set (filtered by effectiveness/suppress)
        if suppress_set and candidates[idx]["name"] in suppress_set:
            continue
        fts_pos += 1
        fts_rank_map[idx] = fts_pos

    # --- RRF fusion ---
    # Union of candidates appearing in either ranking
    all_candidate_idxs = set(vec_rank_map.keys()) | set(fts_rank_map.keys())

    if not all_candidate_idxs:
        return []

    # Miss penalties: rank beyond last position in each list
    vec_miss = len(vector_ranked) + 1
    fts_miss = max(fts_pos, 1) + 1

    scored = []
    for idx in all_candidate_idxs:
        r = candidates[idx]

        # Cosine similarity (already computed for all candidates)
        cosine_sim = float(similarities[idx])

        # min_relevance gate applies to all candidates, including FTS-boosted ones.
        # FTS boosts ranking within the relevant set, not bypasses the gate.
        if cosine_sim < min_relevance:
            continue

        # RRF score
        v_rank = vec_rank_map[idx][0] if idx in vec_rank_map else vec_miss
        f_rank = fts_rank_map.get(idx, fts_miss)
        rrf_score = 1.0 / (RRF_K + v_rank) + 1.0 / (RRF_K + f_rank)

        # Effectiveness × recency modulation (unchanged)
        eff = _causal_adjusted_effectiveness(r)
        last_used = r["last_used"]
        if last_used:
            try:
                days_unused = (_utcnow() - datetime.fromisoformat(last_used)).days
                recency = max(RECENCY_FLOOR, 1.0 - RECENCY_DECAY_PER_DAY * days_unused)
            except (ValueError, TypeError):
                recency = 1.0
        else:
            recency = 0.95  # never-used insights: mild 5% penalty

        final_score = rrf_score * (0.5 + 0.5 * eff) * recency
        scored.append((final_score, cosine_sim, eff, idx))

    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    # Build results from already-fetched full rows (O(1) index lookup)
    results = []
    selected_names = set()
    for score, rel, eff, idx in top:
        row = candidates[idx]
        m = _to_dict(row)
        m["_relevance"] = round(rel, 3)
        m["_effectiveness"] = round(eff, 3)
        m["_score"] = round(score, 3)
        m["_hop"] = 0
        results.append(m)
        selected_names.add(row["name"])

    # --- Graph expansion (1-hop) ---
    if graph_hops >= 1 and results:
        try:
            try:
                from .edges import get_neighbors
            except ImportError:
                from edges import get_neighbors

            top_ids = []
            for score_val, rel, eff, idx in top:
                top_ids.append(candidates[idx]["id"])

            neighbors = get_neighbors(top_ids, limit=limit * 2)
            if neighbors:
                hop_scored = []
                for nbr in neighbors:
                    nbr_name = nbr["name"]
                    if nbr_name in selected_names:
                        continue
                    if suppress_set and nbr_name in suppress_set:
                        continue
                    if not nbr["embedding"]:
                        continue

                    # Compute vector similarity to query
                    nbr_vec = np.frombuffer(nbr["embedding"], dtype=np.float32)
                    vector_sim = float(q_vec @ nbr_vec)
                    if vector_sim < min_relevance:
                        continue

                    nbr_eff = _causal_adjusted_effectiveness(nbr)
                    last_used = nbr["last_used"]
                    if last_used:
                        try:
                            days_unused = (_utcnow() - datetime.fromisoformat(last_used)).days
                            recency = max(RECENCY_FLOOR, 1.0 - RECENCY_DECAY_PER_DAY * days_unused)
                        except (ValueError, TypeError):
                            recency = 1.0
                    else:
                        recency = 0.95

                    hop_score = vector_sim * HOP_DISCOUNT * (0.5 + 0.5 * nbr_eff) * recency
                    hop_scored.append((hop_score, vector_sim, nbr_eff, nbr))
                    selected_names.add(nbr_name)

                # Merge hop results into main results
                for hop_score, rel, eff, nbr_row in hop_scored:
                    m = _to_dict(nbr_row)
                    m["_relevance"] = round(rel, 3)
                    m["_effectiveness"] = round(eff, 3)
                    m["_score"] = round(hop_score, 3)
                    m["_hop"] = 1
                    results.append(m)

                # Re-sort and trim
                results.sort(key=lambda x: -x["_score"])
                results = results[:limit]
        except Exception:
            pass  # graph expansion is best-effort

    return results


def get(name: str) -> Optional[dict]:
    """Get specific insight by name."""
    db = get_db()
    row = db.execute("SELECT * FROM insight WHERE name=?", (name,)).fetchone()
    return _to_dict_full(row) if row else None


def feedback(names: List[str], outcome: str, causal_names: List[str] = None) -> dict:
    """Update effectiveness based on outcome with causal filtering.

    Args:
        names: Insight names that were injected
        outcome: "delivered" or "blocked"
        causal_names: Subset of names that passed causal similarity check.
                      None means treat all as causal (backward compatible).

    Causal insights get standard EMA update.
    Non-causal insights erode 10% toward neutral (0.5), breaking rich-get-richer cycles.

    Returns count of updated insights with causal breakdown.
    """
    if outcome not in ("delivered", "blocked", "plan_complete"):
        return {"updated": 0, "error": "outcome must be 'delivered', 'blocked', or 'plan_complete'"}

    db = get_db()
    now = _utcnow().isoformat()
    updated = 0
    causal_count = 0
    eroded_count = 0

    causal_set = set(causal_names) if causal_names is not None else None
    outcome_value = 1.0 if outcome in ("delivered", "plan_complete") else 0.0

    # Batch-fetch all rows in one query instead of N individual SELECTs
    unique_names = list(set(names))
    placeholders = ",".join("?" for _ in unique_names)
    rows_by_name = {
        r["name"]: r for r in db.execute(
            f"SELECT name, effectiveness, use_count FROM insight WHERE name IN ({placeholders})",
            unique_names
        ).fetchall()
    }

    with write_lock():
        for name in unique_names:
            row = rows_by_name.get(name)
            if not row:
                continue

            old_eff = row["effectiveness"] or 0.5
            is_causal = causal_set is None or name in causal_set

            if is_causal:
                # Standard EMA update for causally relevant insights
                new_eff = old_eff * (1 - FEEDBACK_EMA_WEIGHT) + outcome_value * FEEDBACK_EMA_WEIGHT
                new_eff = max(0.0, min(1.0, new_eff))
                db.execute(
                    "UPDATE insight SET effectiveness=?, use_count=use_count+1, "
                    "causal_hits=causal_hits+1, last_used=?, last_feedback_at=? WHERE name=?",
                    (new_eff, now, now, name)
                )
                causal_count += 1
            else:
                # Erode toward neutral: 10% toward 0.5 (above-neutral only)
                # Don't increment use_count — erosion is the penalty, not a "use"
                # (incrementing use_count without causal_hits compounds with
                # _causal_adjusted_effectiveness read-time penalty)
                # Asymmetric: below-0.5 insights stay bad until positive causal feedback
                if old_eff > 0.5:
                    new_eff = old_eff + (0.5 - old_eff) * EROSION_RATE
                else:
                    new_eff = old_eff
                new_eff = max(0.0, min(1.0, new_eff))
                db.execute(
                    "UPDATE insight SET effectiveness=?, last_used=? WHERE name=?",
                    (new_eff, now, name)
                )
                eroded_count += 1

            updated += 1
        db.commit()

    return {
        "updated": updated,
        "outcome": outcome,
        "names": unique_names,
        "causal": causal_count,
        "eroded": eroded_count
    }


def decay(unused_days: int = 30) -> dict:
    """Decay dormant insights toward neutral effectiveness.

    Affects insights that haven't been used in unused_days.
    Moves effectiveness toward 0.5 (neutral).

    Returns count of affected insights.
    """
    db = get_db()
    cutoff = (_utcnow() - timedelta(days=unused_days)).isoformat()

    with write_lock():
        # Move effectiveness toward 0.5 (above-0.5 only)
        # Asymmetric: bad insights should not drift upward without evidence
        cursor = db.execute(f"""
            UPDATE insight
            SET effectiveness = effectiveness * {1 - DECAY_RATE} + 0.5 * {DECAY_RATE}
            WHERE use_count > 0
            AND effectiveness > 0.5
            AND (last_used IS NULL OR last_used < ?)
        """, (cutoff,))
        db.commit()
        affected = cursor.rowcount

    return {"decayed": affected, "threshold_days": unused_days}


def prune(min_effectiveness: float = 0.25, min_uses: int = 3) -> dict:
    """Remove insights that have proven unhelpful.

    Uses causal-adjusted effectiveness for threshold check — an insight with
    raw eff 0.50 but use_count=20/causal_hits=0 → adjusted eff 0.15 → pruned.

    Also cleans orphan insights (NULL embedding, never used, older than 7 days).
    """
    db = get_db()
    rows = db.execute(
        "SELECT name, effectiveness, use_count, causal_hits FROM insight WHERE use_count >= ?",
        (min_uses,)
    ).fetchall()

    to_remove = []
    for r in rows:
        adj_eff = _causal_adjusted_effectiveness(r)
        if adj_eff < min_effectiveness:
            to_remove.append(r["name"])

    # Orphan cleanup: NULL-embedding, never used, older than 7 days
    orphan_cutoff = (_utcnow() - timedelta(days=7)).isoformat()
    orphans = db.execute(
        "SELECT name FROM insight WHERE embedding IS NULL AND use_count = 0 AND created_at < ?",
        (orphan_cutoff,)
    ).fetchall()
    orphan_names = [r["name"] for r in orphans]

    # Ghost cleanup: valid embedding, never used, older than 60 days
    ghost_cutoff = (_utcnow() - timedelta(days=60)).isoformat()
    ghosts = db.execute(
        "SELECT name FROM insight WHERE embedding IS NOT NULL AND use_count = 0 AND created_at < ?",
        (ghost_cutoff,)
    ).fetchall()
    ghost_names = [r["name"] for r in ghosts]

    all_remove = to_remove + orphan_names + ghost_names
    with write_lock():
        if all_remove:
            placeholders = ",".join("?" for _ in all_remove)
            # Look up IDs before deletion for edge cleanup
            deleted_ids = [
                r["id"] for r in db.execute(
                    f"SELECT id FROM insight WHERE name IN ({placeholders})", all_remove
                ).fetchall()
            ]
            db.execute(f"DELETE FROM insight WHERE name IN ({placeholders})", all_remove)
            # Clean orphaned edges (manual CASCADE — FK pragma not enabled)
            if deleted_ids:
                id_ph = ",".join("?" for _ in deleted_ids)
                db.execute(
                    f"DELETE FROM insight_edges WHERE src_id IN ({id_ph}) OR dst_id IN ({id_ph})",
                    deleted_ids + deleted_ids
                )
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]
    return {
        "pruned": len(to_remove),
        "orphans_cleaned": len(orphan_names),
        "ghosts_cleaned": len(ghost_names),
        "remaining": remaining,
        "removed": to_remove + orphan_names + ghost_names
    }


def count() -> int:
    """Return total number of insights. Lightweight alternative to health()."""
    db = get_db()
    return db.execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]


def health() -> dict:
    """Check learning system health."""
    db = get_db()
    cutoff = (_utcnow() - timedelta(hours=1)).isoformat()

    # Single aggregate query replaces 4 separate queries
    agg = db.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN use_count > 0 THEN 1 ELSE 0 END) as with_feedback,
            SUM(CASE WHEN last_feedback_at IS NOT NULL AND last_feedback_at > ? THEN 1 ELSE 0 END) as recent_fb,
            AVG(CASE WHEN use_count > 0 THEN effectiveness END) as avg_eff,
            SUM(CASE WHEN use_count > 0 THEN causal_hits ELSE 0 END) as ch,
            SUM(CASE WHEN use_count > 0 THEN use_count ELSE 0 END) as uc
        FROM insight
    """, (cutoff,)).fetchone()

    total = agg["total"]
    with_feedback = agg["with_feedback"] or 0
    recent_fb = agg["recent_fb"] or 0
    avg_eff = agg["avg_eff"] if agg["avg_eff"] is not None else 0.5
    total_causal = agg["ch"] or 0
    total_uses = agg["uc"] or 0
    causal_ratio = round(total_causal / total_uses, 3) if total_uses > 0 else 0.0

    # Tag distribution (lightweight — tags stored as JSON arrays)
    tag_rows = db.execute("""
        SELECT j.value as tag, COUNT(*) as cnt
        FROM insight, json_each(insight.tags) j
        WHERE insight.tags IS NOT NULL AND insight.tags != '[]'
        GROUP BY j.value
        ORDER BY cnt DESC
    """).fetchall()
    by_tag = {r["tag"]: r["cnt"] for r in tag_rows}

    # Edge statistics
    try:
        edge_agg = db.execute("""
            SELECT COUNT(*) as total_edges,
                   COUNT(DISTINCT src_id) as src_count,
                   COUNT(DISTINCT dst_id) as dst_count
            FROM insight_edges
        """).fetchone()
        total_edges = edge_agg["total_edges"]
        connected_insights = edge_agg["src_count"] + edge_agg["dst_count"]
        # Deduplicate: some IDs appear in both src and dst
        if total_edges > 0:
            unique_connected = db.execute("""
                SELECT COUNT(*) as c FROM (
                    SELECT src_id AS id FROM insight_edges
                    UNION
                    SELECT dst_id AS id FROM insight_edges
                )
            """).fetchone()["c"]
        else:
            unique_connected = 0
        connected_ratio = round(unique_connected / total, 3) if total > 0 else 0.0
        avg_edges = round(total_edges / total, 2) if total > 0 else 0.0
    except Exception:
        total_edges = 0
        connected_ratio = 0.0
        avg_edges = 0.0

    loop_closed = total > 0 and with_feedback > 0
    issues = []
    if total == 0:
        issues.append("No insights yet")
    elif with_feedback == 0:
        issues.append("No feedback recorded - learning loop not closed")

    return {
        "status": "HEALTHY" if loop_closed and not issues else "NEEDS_ATTENTION",
        "total_insights": total,
        "total_edges": total_edges,
        "connected_ratio": connected_ratio,
        "avg_edges_per_insight": avg_edges,
        "by_tag": by_tag,
        "effectiveness": round(avg_eff, 3),
        "with_feedback": with_feedback,
        "recent_feedback": recent_fb,
        "causal_ratio": causal_ratio,
        "issues": issues
    }


# =============================================================================
# CLI
# =============================================================================

def _log_verbose(cmd: str, args: dict, result: dict) -> None:
    """Print structured log to stderr when --verbose is enabled."""
    log_entry = {
        "timestamp": _utcnow().isoformat(),
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
    p.add_argument("--db", help="Override database path")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("store")
    s.add_argument("--content", required=True, help="Insight content")
    s.add_argument("--tags", default="[]", help="JSON array of tags")

    s = sub.add_parser("recall")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--min-effectiveness", type=float, default=0.0)
    s.add_argument("--min-relevance", type=float, default=MIN_RELEVANCE_DEFAULT,
                   help=f"Minimum cosine similarity threshold (default: {MIN_RELEVANCE_DEFAULT})")
    s.add_argument("--suppress-names", default=None,
                   help="JSON list of insight names to exclude from results (for diversity)")
    s.add_argument("--graph-hops", type=int, default=0,
                   help="Expand results via graph neighbors (0=off, 1=1-hop)")

    s = sub.add_parser("get")
    s.add_argument("name")

    s = sub.add_parser("feedback")
    s.add_argument("--names", required=True, help="JSON list of insight names")
    s.add_argument("--outcome", required=True, choices=["delivered", "blocked", "plan_complete"])
    s.add_argument("--causal-names", default=None, help="JSON list of causally relevant insight names (subset of --names)")

    s = sub.add_parser("decay")
    s.add_argument("--days", type=int, default=30)

    s = sub.add_parser("prune")
    s.add_argument("--threshold", type=float, default=0.25, dest="min_effectiveness")
    s.add_argument("--min-uses", type=int, default=3)

    sub.add_parser("health")

    s = sub.add_parser("neighbors")
    s.add_argument("name", help="Insight name to find neighbors for")
    s.add_argument("--limit", type=int, default=5)
    s.add_argument("--relation", default=None, help="Filter by relation type (similar, led_to)")

    args = p.parse_args()

    # Override DB path if specified
    if args.db:
        import os
        import db.connection as conn_module
        resolved = str(Path(args.db).resolve())
        os.environ["HELIX_DB_PATH"] = resolved
        conn_module.DB_PATH = resolved
        conn_module.reset_db()

    r = None

    if args.cmd == "store":
        tags = json.loads(args.tags) if args.tags else []
        r = store(args.content, tags)
    elif args.cmd == "recall":
        suppress = json.loads(args.suppress_names) if args.suppress_names else None
        r = recall(args.query, args.limit, args.min_effectiveness, args.min_relevance,
                   suppress_names=suppress, graph_hops=args.graph_hops)
    elif args.cmd == "get":
        r = get(args.name)
        if r is None:
            r = {"error": "not found"}
    elif args.cmd == "feedback":
        causal = json.loads(args.causal_names) if args.causal_names else None
        r = feedback(json.loads(args.names), args.outcome, causal_names=causal)
    elif args.cmd == "decay":
        r = decay(args.days)
    elif args.cmd == "prune":
        r = prune(min_effectiveness=args.min_effectiveness, min_uses=args.min_uses)
    elif args.cmd == "health":
        r = health()
    elif args.cmd == "neighbors":
        db = get_db()
        row = db.execute("SELECT id FROM insight WHERE name = ?", (args.name,)).fetchone()
        if not row:
            r = {"error": f"insight '{args.name}' not found"}
        else:
            try:
                from edges import get_neighbors
            except ImportError:
                from .edges import get_neighbors
            nbrs = get_neighbors([row["id"]], relation=args.relation, limit=args.limit)
            r = []
            for nbr in nbrs:
                d = _to_dict(nbr)
                d["edge_weight"] = round(nbr["edge_weight"], 3)
                d["edge_relation"] = nbr["edge_relation"]
                r.append(d)

    if args.verbose and r is not None:
        cmd_args = {k: v for k, v in vars(args).items() if k not in ('cmd', 'verbose', 'db')}
        _log_verbose(args.cmd, cmd_args, r)

    print(json.dumps(r, indent=2))
