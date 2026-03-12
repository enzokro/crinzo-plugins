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
Feedback EMA weight: 0.2 (~3 positive outcomes to move 0.5 -> 0.6)
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

# Scoring: multiplicative -- effectiveness modulates relevance, not competes with it
# score = relevance * (0.5 + 0.5 * effectiveness)
DUPLICATE_THRESHOLD = 0.85
MIN_RELEVANCE_DEFAULT = 0.35  # arctic-embed-m-v1.5: unrelated 0.05-0.25, related 0.35+
CAUSAL_SIMILARITY_THRESHOLD = 0.50  # For feedback attribution filtering (tighter than 0.40)
CAUSAL_WEIGHT_RAMP = CAUSAL_SIMILARITY_THRESHOLD  # Weight normalizer: 0.0 at threshold, 1.0 at sim=1.0

# Graph: auto-linking and expansion
RELATED_THRESHOLD = 0.60    # Semantic similarity floor for auto-linking (below DUPLICATE_THRESHOLD)
MAX_AUTOLINK_EDGES = 5      # Cap edges per new insight
HOP_DISCOUNT = 0.7          # Score multiplier for graph-adjacent insights (PageRank-informed)

# Tuning parameters -- extracted from inline for visibility
FEEDBACK_EMA_WEIGHT = 0.2       # Learning rate for causal feedback (was 0.1; ~3 outcomes to move 0.5->0.6)
DECAY_RATE = 0.1                # Rate dormant insights drift toward neutral per session_end
EROSION_RATE = 0.09             # Rate non-causal insights drift toward neutral (loss-aversion calibrated: EMA/2.25)
CAUSAL_ADJUSTMENT_FLOOR = 0.33  # Minimum multiplier for causal hit ratio (at-chance for 3-use minimum)
CAUSAL_MIN_USES = 3             # Uses before causal adjustment kicks in
RECENCY_DECAY_PER_DAY = 0.003  # 0.3% score penalty per day unused (231d half-life)
RECENCY_FLOOR = 0.85            # Maximum 15% recency penalty; floor reached at ~50 days
RRF_K = 60                      # Reciprocal Rank Fusion smoothing constant
VELOCITY_PER_USE = 0.02    # Score boost per recent feedback event
VELOCITY_CAP = 0.10        # Maximum 10% velocity boost (5 recent uses to cap)
VELOCITY_WINDOW_DAYS = 14  # Window for "recent" usage
GENERALITY_SPREAD_CAP = 0.30       # Spread at which insight is "fully general"
GENERALITY_DECAY_DISCOUNT = 0.50   # Max decay rate reduction for general insights (0.1 → 0.05)
GENERALITY_MIN_SPREAD = 0.05       # Below this, insufficient diversity data

# Outcome values for feedback
OUTCOME_VALUES = {"delivered": 1.0, "blocked": 0.0, "partial": 0.3, "plan_complete": 1.0}

# Support both module and script execution
try:
    from ..db.connection import get_db, write_lock
    from .embeddings import embed, to_blob, build_embedding_matrix
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import embed, to_blob, build_embedding_matrix

# Edge imports are deferred to avoid circular import (edges.py imports _utcnow from core.py)
def _edge_imports():
    try:
        from .edges import add_edges, get_neighbors, delete_edges_for
    except ImportError:
        from edges import add_edges, get_neighbors, delete_edges_for
    return add_edges, get_neighbors, delete_edges_for


# =============================================================================
# HELPERS
# =============================================================================

def _utcnow() -> datetime:
    """Return current UTC time as naive datetime (no tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50]


def _clamp01(v):
    return max(0.0, min(1.0, v))


def _recency(last_used):
    """Compute recency score from last_used timestamp."""
    if not last_used:
        return 0.95
    try:
        days = (_utcnow() - datetime.fromisoformat(last_used)).days
        return max(RECENCY_FLOOR, 1.0 - RECENCY_DECAY_PER_DAY * days)
    except (ValueError, TypeError):
        return 1.0


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
    return eff * max(CAUSAL_ADJUSTMENT_FLOOR, causal_hits / use_count)


def _to_dict(row) -> dict:
    """Convert database row to insight dict."""
    try:
        tags = json.loads(row["tags"]) if row["tags"] else []
    except Exception:
        tags = []
    return {
        "name": row["name"],
        "content": row["content"],
        "effectiveness": round(_effectiveness(row), 3),
        "use_count": row["use_count"] or 0,
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "tags": tags,
        "causal_hits": row["causal_hits"] or 0,
        "recent_uses": row["recent_uses"] or 0,
        "context_spread": round(row["context_spread"], 4) if row["context_spread"] is not None else None,
    }


def _make_result(row, relevance, eff, score, hop=0):
    """Build a recall result dict from a row."""
    m = _to_dict(row)
    m["_id"] = row["id"]
    m["_relevance"] = round(relevance, 3)
    m["_effectiveness"] = round(eff, 3)
    m["_score"] = round(score, 3)
    m["_hop"] = hop
    return m


# =============================================================================
# FTS5 HELPERS
# =============================================================================

_FTS5_RESERVED = frozenset({"AND", "OR", "NOT", "NEAR"})


def _build_fts_query(query):
    """Sanitize query into FTS5 MATCH expression. Keeps hyphens for compound terms."""
    tokens = [f'"{c}"' for w in query.split()
              if (c := re.sub(r"[^a-zA-Z0-9\-]", "", w)) and c.upper() not in _FTS5_RESERVED]
    return " OR ".join(tokens)


def _fts_search(db, query, limit):
    """FTS5 keyword search. Returns [(rowid, rank), ...]. Empty on error."""
    if not (fts_expr := _build_fts_query(query)):
        return []
    try:
        return db.execute(
            "SELECT rowid, rank FROM insight_fts WHERE insight_fts MATCH ? ORDER BY rank LIMIT ?",
            (fts_expr, limit)).fetchall()
    except Exception:
        return []


# =============================================================================
# STORE HELPERS
# =============================================================================

def _merge_duplicate(db, match_name, content, new_emb, tags):
    """Merge new content into existing duplicate insight. Returns result dict."""
    now = _utcnow().isoformat()
    with write_lock():
        existing = db.execute(
            "SELECT content, effectiveness FROM insight WHERE name = ?",
            (match_name,)
        ).fetchone()
        if existing and (
            len(content) > len(existing["content"])
            or (existing["effectiveness"] or 0.5) < 0.5
        ):
            db.execute(
                "UPDATE insight SET content=?, embedding=?, tags=?, last_used=? WHERE name=?",
                (content, to_blob(new_emb), json.dumps(tags), now, match_name)
            )
        else:
            db.execute(
                "UPDATE insight SET last_used=? WHERE name=?",
                (now, match_name)
            )
        db.commit()
    return {"status": "merged", "name": match_name, "reason": "similar exists"}


def _autolink(new_id, dedup_rows, dedup_sims):
    """Create edges from new insight to semantically related existing insights."""
    try:
        import numpy as np
        candidates = [
            (dedup_rows[i]["id"], float(sim))
            for i, sim in enumerate(dedup_sims)
            if RELATED_THRESHOLD <= float(sim) < DUPLICATE_THRESHOLD
        ]
        candidates.sort(key=lambda x: -x[1])
        edges = [(new_id, cid, w, "similar") for cid, w in candidates[:MAX_AUTOLINK_EDGES]]
        if edges:
            _edge_imports()[0](edges)
    except Exception as e:
        print(f"helix: graph: {e}", file=sys.stderr)


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

    # Security scan before any processing
    try:
        from .scanner import scan as _scan_content
    except ImportError:
        from scanner import scan as _scan_content
    is_safe, scan_reason = _scan_content(content)
    if not is_safe:
        return {"status": "rejected", "name": "", "reason": f"security: {scan_reason}"}

    content = content.strip()
    tags = tags or []

    # Check for semantic duplicate (vectorized)
    new_emb = embed(content, is_query=False)
    dedup_rows = None
    dedup_sims = None
    skip_dedup = tags and ("user-provided" in tags or "user-preference" in tags)
    if new_emb and not skip_dedup:
        db = get_db()
        dedup_rows = db.execute("SELECT id, name, embedding FROM insight WHERE embedding IS NOT NULL").fetchall()
        if dedup_rows:
            import numpy as np
            q_vec = np.array(new_emb, dtype=np.float32)
            mat = build_embedding_matrix(r["embedding"] for r in dedup_rows)
            dedup_sims = mat @ q_vec
            best_idx = int(np.argmax(dedup_sims))
            if dedup_sims[best_idx] >= DUPLICATE_THRESHOLD:
                return _merge_duplicate(db, dedup_rows[best_idx]["name"], content, new_emb, tags)

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
        _autolink(new_id, dedup_rows, dedup_sims)

    return {"status": "added", "name": name, "reason": ""}


def recall(query: str, limit: int = 5, min_effectiveness: float = 0.0,
           min_relevance: float = MIN_RELEVANCE_DEFAULT,
           suppress_names: List[str] = None,
           graph_hops: int = 1) -> List[dict]:
    """Recall insights by hybrid vector + keyword search with RRF fusion.

    Args:
        query: Search query
        limit: Maximum results
        min_effectiveness: Minimum effectiveness threshold
        min_relevance: Minimum cosine similarity (0.35 default). "No memory" beats "wrong memory."
        graph_hops: Expand results via graph neighbors (0=off, 1=1-hop). Default 1.

    Scoring: rrf_score * (0.5 + 0.5 * eff) * recency
    Returns list with _relevance, _score, _hop fields.
    """
    db = get_db()

    q_emb = embed(query, is_query=True)
    if q_emb is None:
        rows = db.execute(
            "SELECT * FROM insight ORDER BY effectiveness DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [_to_dict(r) for r in rows]

    rows = db.execute(
        "SELECT * FROM insight WHERE embedding IS NOT NULL AND effectiveness >= ?",
        (min_effectiveness,)
    ).fetchall()
    if not rows:
        return []

    suppress_set = set(suppress_names) if suppress_names else set()
    candidates = [r for r in rows if r["name"] not in suppress_set]
    if not candidates:
        return []

    # Vectorized cosine: single matrix multiply for all candidates
    import numpy as np
    q_vec = np.array(q_emb, dtype=np.float32)
    mat = build_embedding_matrix(r["embedding"] for r in candidates)
    similarities = mat @ q_vec

    # --- Vector ranking ---
    vector_ranked = sorted(
        ((i, float(similarities[i])) for i in range(len(candidates))),
        key=lambda x: -x[1]
    )
    vector_ranked = [(i, sim) for i, sim in vector_ranked if sim >= min_relevance]
    vec_rank_map = {idx: (pos, sim) for pos, (idx, sim) in enumerate(vector_ranked, 1)}

    # --- FTS5 keyword ranking ---
    fts_rows = _fts_search(db, query, limit * 3)
    candidate_id_to_idx = {r["id"]: i for i, r in enumerate(candidates)}
    fts_rank_map = {}
    fts_pos = 0
    for fts_row in fts_rows:
        rowid = fts_row["rowid"] if isinstance(fts_row, dict) or hasattr(fts_row, "keys") else fts_row[0]
        idx = candidate_id_to_idx.get(rowid)
        if idx is not None:
            fts_pos += 1
            fts_rank_map[idx] = fts_pos

    # --- RRF fusion ---
    all_candidate_idxs = set(vec_rank_map.keys()) | set(fts_rank_map.keys())
    if not all_candidate_idxs:
        return []

    vec_miss = len(vector_ranked) + 1
    fts_miss = max(fts_pos, 1) + 1

    scored = []
    for idx in all_candidate_idxs:
        cosine_sim = float(similarities[idx])
        if cosine_sim < min_relevance:
            continue

        v_rank = vec_rank_map[idx][0] if idx in vec_rank_map else vec_miss
        f_rank = fts_rank_map.get(idx, fts_miss)
        rrf_score = 1.0 / (RRF_K + v_rank) + 1.0 / (RRF_K + f_rank)

        eff = _causal_adjusted_effectiveness(candidates[idx])
        recency = _recency(candidates[idx]["last_used"])
        velocity_boost = min(VELOCITY_CAP, (candidates[idx]["recent_uses"] or 0) * VELOCITY_PER_USE)
        final_score = rrf_score * (0.5 + 0.5 * eff) * recency * (1.0 + velocity_boost)
        scored.append((final_score, cosine_sim, eff, idx))

    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    results = []
    selected_names = set()
    for score, rel, eff, idx in top:
        results.append(_make_result(candidates[idx], rel, eff, score, hop=0))
        selected_names.add(candidates[idx]["name"])

    # --- Graph expansion (1-hop) ---
    if graph_hops >= 1 and results:
        try:
            top_ids = [candidates[idx]["id"] for _, _, _, idx in top]
            _, _get_neighbors, _ = _edge_imports()
            neighbors = _get_neighbors(top_ids, limit=limit * 2)
            if neighbors:
                hop_scored = []
                for nbr in neighbors:
                    nbr_name = nbr["name"]
                    if nbr_name in selected_names or nbr_name in suppress_set:
                        continue
                    if not nbr["embedding"]:
                        continue

                    vector_sim = float(q_vec @ np.frombuffer(nbr["embedding"], dtype=np.float32))
                    if vector_sim < min_relevance:
                        continue

                    nbr_eff = _causal_adjusted_effectiveness(nbr)
                    recency = _recency(nbr["last_used"])
                    hop_score = vector_sim * HOP_DISCOUNT * (0.5 + 0.5 * nbr_eff) * recency
                    hop_scored.append((hop_score, vector_sim, nbr_eff, nbr))
                    selected_names.add(nbr_name)

                for hop_score, rel, eff, nbr_row in hop_scored:
                    results.append(_make_result(nbr_row, rel, eff, hop_score, hop=1))

                results.sort(key=lambda x: -x["_score"])
                results = results[:limit]
        except Exception as e:
            print(f"helix: graph: {e}", file=sys.stderr)

    return results


def get(name: str) -> Optional[dict]:
    """Get specific insight by name."""
    row = get_db().execute("SELECT * FROM insight WHERE name=?", (name,)).fetchone()
    if not row:
        return None
    return _to_dict(row)


def _update_context_spread(db, name, ctx_emb_bytes, n):
    """Incrementally update context centroid and spread (Welford's for cosine space).

    Tracks semantic diversity of causal contexts. High spread = principle (general).
    Low spread = observation (narrow). Used to modulate decay rate.
    """
    import numpy as np
    ctx_vec = np.frombuffer(ctx_emb_bytes, dtype=np.float32).copy()

    row = db.execute(
        "SELECT context_centroid, context_spread FROM insight WHERE name = ?",
        (name,)
    ).fetchone()
    if not row:
        return

    if row["context_centroid"] is None:
        # First causal context: set centroid, spread = 0
        db.execute(
            "UPDATE insight SET context_centroid=?, context_spread=0.0 WHERE name=?",
            (ctx_vec.astype(np.float32).tobytes(), name)
        )
    else:
        old_centroid = np.frombuffer(row["context_centroid"], dtype=np.float32).copy()
        old_spread = row["context_spread"] or 0.0

        # Welford's: update running centroid
        new_centroid = old_centroid * ((n - 1) / n) + ctx_vec * (1.0 / n)
        # Re-normalize to unit sphere (prevent drift)
        norm = np.linalg.norm(new_centroid)
        if norm > 0:
            new_centroid = new_centroid / norm

        # Incremental variance in cosine space (n >= 3 for stability)
        if n >= 3:
            dist = 1.0 - float(np.dot(ctx_vec, new_centroid))
            new_spread = old_spread * ((n - 2) / (n - 1)) + max(0.0, dist) / (n - 1)
        else:
            new_spread = old_spread

        db.execute(
            "UPDATE insight SET context_centroid=?, context_spread=? WHERE name=?",
            (new_centroid.astype(np.float32).tobytes(), round(new_spread, 6), name)
        )


def _apply_causal_update(db, name, row, weight, outcome_value, now, context_embedding=None):
    """Apply weighted causal feedback: EMA update + velocity + generality tracking."""
    old_eff = row["effectiveness"] or 0.5
    new_eff = _clamp01(old_eff * (1 - FEEDBACK_EMA_WEIGHT * weight) + outcome_value * FEEDBACK_EMA_WEIGHT * weight)
    db.execute(
        "UPDATE insight SET effectiveness=?, use_count=use_count+1, "
        "causal_hits=causal_hits+1, recent_uses=recent_uses+1, last_used=?, last_feedback_at=? WHERE name=?",
        (new_eff, now, now, name)
    )
    if context_embedding is not None:
        new_causal_hits = (row["causal_hits"] or 0) + 1
        try:
            _update_context_spread(db, name, context_embedding, new_causal_hits)
        except Exception:
            pass  # Best-effort: don't fail feedback on spread computation error


def _apply_erosion(db, name, row, now):
    """Apply non-causal erosion: drift above-0.5 insights toward neutral."""
    old_eff = row["effectiveness"] or 0.5
    # Asymmetric: below-0.5 insights stay bad until positive causal feedback
    new_eff = _clamp01(old_eff + (0.5 - old_eff) * EROSION_RATE if old_eff > 0.5 else old_eff)
    db.execute(
        "UPDATE insight SET effectiveness=?, last_used=? WHERE name=?",
        (new_eff, now, name)
    )


def feedback(names: List[str], outcome: str, causal_names: List[str] = None, context_embedding=None) -> dict:
    """Update effectiveness based on outcome with causal filtering.

    Args:
        names: Insight names that were injected
        outcome: "delivered" or "blocked"
        causal_names: Subset of names that passed causal similarity check.
                      None means treat all as causal (backward compatible).
        context_embedding: bytes (f32 blob) of the task context embedding for generality tracking.

    Returns count of updated insights with causal breakdown.
    """
    if outcome not in OUTCOME_VALUES:
        return {"updated": 0, "error": f"outcome must be one of {sorted(OUTCOME_VALUES.keys())}"}

    db = get_db()
    now = _utcnow().isoformat()
    updated = 0
    causal_count = 0
    eroded_count = 0

    if causal_names is not None:
        if causal_names and isinstance(causal_names[0], tuple):
            causal_map = {n: max(0.0, (s - CAUSAL_WEIGHT_RAMP) / (1.0 - CAUSAL_WEIGHT_RAMP))
                          for n, s in causal_names}
            causal_set = set(causal_map.keys())
        else:
            causal_map = {n: 1.0 for n in causal_names}
            causal_set = set(causal_names)
    else:
        causal_set = None
        causal_map = None
    outcome_value = OUTCOME_VALUES[outcome]

    # Batch-fetch all rows in one query instead of N individual SELECTs
    unique_names = list(set(names))
    placeholders = ",".join("?" for _ in unique_names)
    rows_by_name = {
        r["name"]: r for r in db.execute(
            f"SELECT name, effectiveness, use_count, causal_hits FROM insight WHERE name IN ({placeholders})",
            unique_names
        ).fetchall()
    }

    with write_lock():
        for name in unique_names:
            row = rows_by_name.get(name)
            if not row:
                continue

            is_causal = causal_set is None or name in causal_set

            if is_causal:
                weight = causal_map[name] if causal_map else 1.0
                _apply_causal_update(db, name, row, weight, outcome_value, now, context_embedding)
                causal_count += 1
            else:
                _apply_erosion(db, name, row, now)
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
    """Decay dormant insights toward neutral effectiveness."""
    db = get_db()
    cutoff = (_utcnow() - timedelta(days=unused_days)).isoformat()

    with write_lock():
        # Decay with generality modulation
        rows = db.execute(
            "SELECT name, effectiveness, context_spread FROM insight "
            "WHERE use_count > 0 AND effectiveness > 0.5 "
            "AND (last_used IS NULL OR last_used < ?)",
            (cutoff,)
        ).fetchall()

        decayed = 0
        for row in rows:
            spread = row["context_spread"]
            if spread is not None and spread >= GENERALITY_MIN_SPREAD:
                generality = min(1.0, spread / GENERALITY_SPREAD_CAP)
                rate = DECAY_RATE * (1.0 - GENERALITY_DECAY_DISCOUNT * generality)
            else:
                rate = DECAY_RATE
            new_eff = row["effectiveness"] * (1 - rate) + 0.5 * rate
            db.execute("UPDATE insight SET effectiveness=? WHERE name=?",
                       (new_eff, row["name"]))
            decayed += 1
        db.commit()

        # Reset stale velocity
        velocity_cutoff = (_utcnow() - timedelta(days=VELOCITY_WINDOW_DAYS)).isoformat()
        db.execute(
            "UPDATE insight SET recent_uses = 0 "
            "WHERE last_feedback_at IS NOT NULL AND last_feedback_at < ? AND recent_uses > 0",
            (velocity_cutoff,)
        )
        db.commit()

    return {"decayed": decayed, "threshold_days": unused_days}


def prune(min_effectiveness: float = 0.25, min_uses: int = 3) -> dict:
    """Remove insights that have proven unhelpful.

    Uses causal-adjusted effectiveness for threshold check.
    Also cleans orphan and ghost insights.
    """
    db = get_db()
    rows = db.execute(
        "SELECT name, effectiveness, use_count, causal_hits FROM insight WHERE use_count >= ?",
        (min_uses,)
    ).fetchall()

    to_remove = [r["name"] for r in rows if _causal_adjusted_effectiveness(r) < min_effectiveness]

    # Orphan cleanup: NULL-embedding, never used, older than 7 days
    orphan_cutoff = (_utcnow() - timedelta(days=7)).isoformat()
    orphan_names = [r["name"] for r in db.execute(
        "SELECT name FROM insight WHERE embedding IS NULL AND use_count = 0 AND created_at < ?",
        (orphan_cutoff,)
    ).fetchall()]

    # Ghost cleanup: valid embedding, never used, older than 60 days
    ghost_cutoff = (_utcnow() - timedelta(days=60)).isoformat()
    ghost_names = [r["name"] for r in db.execute(
        "SELECT name FROM insight WHERE embedding IS NOT NULL AND use_count = 0 AND created_at < ?",
        (ghost_cutoff,)
    ).fetchall()]

    all_remove = to_remove + orphan_names + ghost_names
    with write_lock():
        if all_remove:
            placeholders = ",".join("?" for _ in all_remove)
            deleted_ids = [
                r["id"] for r in db.execute(
                    f"SELECT id FROM insight WHERE name IN ({placeholders})", all_remove
                ).fetchall()
            ]
            db.execute(f"DELETE FROM insight WHERE name IN ({placeholders})", all_remove)
            if deleted_ids:
                _edge_imports()[2](deleted_ids)
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
    return get_db().execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]


def health() -> dict:
    """Check learning system health."""
    db = get_db()
    cutoff = (_utcnow() - timedelta(hours=1)).isoformat()

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

    # Tag distribution
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
    if total > 10 and with_feedback / total < 0.3:
        issues.append("Low loop coverage — most insights haven't been through the feedback loop")

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
        "loop_coverage": round(with_feedback / total, 3) if total else 0.0,
        "causal_ratio": causal_ratio,
        "issues": issues
    }


def neighbors(name: str, limit: int = 5, relation: str = None) -> list:
    """Find graph neighbors for a named insight."""
    db = get_db()
    row = db.execute("SELECT id FROM insight WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    _, _get_neighbors, _ = _edge_imports()
    nbrs = _get_neighbors([row["id"]], relation=relation, limit=limit)
    results = []
    for nbr in nbrs:
        d = _to_dict(nbr)
        d["edge_weight"] = round(nbr["edge_weight"], 3)
        d["edge_relation"] = nbr["edge_relation"]
        results.append(d)
    return results


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
    s.add_argument("--graph-hops", type=int, default=1,
                   help="Expand results via graph neighbors (0=off, 1=1-hop)")

    s = sub.add_parser("get")
    s.add_argument("name")

    s = sub.add_parser("feedback")
    s.add_argument("--names", required=True, help="JSON list of insight names")
    s.add_argument("--outcome", required=True, choices=sorted(OUTCOME_VALUES.keys()))
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

    sub.add_parser("stats", help="System statistics for tuning calibration")

    args = p.parse_args()

    # Override DB path if specified
    if args.db:
        import os
        try:
            from ..db import connection as conn_module
        except ImportError:
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
        r = neighbors(args.name, limit=args.limit, relation=args.relation)
        if r is None:
            r = {"error": f"insight '{args.name}' not found"}
    elif args.cmd == "stats":
        try:
            from .stats import full_stats
        except ImportError:
            from stats import full_stats
        r = full_stats()

    if args.verbose and r is not None:
        cmd_args = {k: v for k, v in vars(args).items() if k not in ('cmd', 'verbose', 'db')}
        _log_verbose(args.cmd, cmd_args, r)

    print(json.dumps(r, indent=2))
