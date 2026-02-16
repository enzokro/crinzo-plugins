#!/usr/bin/env python3
"""Memory: unified insight storage and retrieval.

Core API (8 primitives):
- store(content, tags) -> {"status": "added"|"merged", "name": str}
- recall(query, limit, suppress_names) -> insights sorted by 0.78*relevance + 0.22*causal_eff
- feedback(names, outcome, causal_names) -> update effectiveness with causal filtering
- decay(unused_days) -> decay dormant insights
- prune(min_effectiveness, min_uses) -> remove low-performing insights
- count() -> total insight count (lightweight)
- health() -> system status

Scoring formula:
    score = (0.78 * relevance) + (0.22 * effectiveness)
Feedback EMA weight: 0.2 (~3 positive outcomes to move 0.5 → 0.6)
"""

import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List

import numpy as np

# Scoring constants
SCORE_WEIGHTS = {'relevance': 0.78, 'effectiveness': 0.22}
DUPLICATE_THRESHOLD = 0.85
MIN_RELEVANCE_DEFAULT = 0.35  # arctic-embed-m-v1.5: unrelated 0.05-0.25, related 0.35+
CAUSAL_SIMILARITY_THRESHOLD = 0.40  # For feedback attribution filtering

# Tuning parameters — extracted from inline for visibility
FEEDBACK_EMA_WEIGHT = 0.2       # Learning rate for causal feedback (was 0.1; ~3 outcomes to move 0.5→0.6)
DECAY_RATE = 0.1                # Rate dormant insights drift toward neutral per session_end
EROSION_RATE = 0.10             # Rate non-causal insights drift toward neutral per feedback
CAUSAL_ADJUSTMENT_FLOOR = 0.3   # Minimum multiplier for causal hit ratio
CAUSAL_MIN_USES = 3             # Uses before causal adjustment kicks in

# Support both module and script execution
try:
    from ..db.connection import get_db, write_lock
    from .embeddings import embed, to_blob
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from db.connection import get_db, write_lock
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import embed, to_blob


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
    if new_emb:
        db = get_db()
        rows = db.execute("SELECT name, embedding FROM insight WHERE embedding IS NOT NULL").fetchall()
        if rows:
            q_vec = np.array(new_emb, dtype=np.float32)
            names = [r["name"] for r in rows]
            mat = np.frombuffer(b''.join(r["embedding"] for r in rows),
                                dtype=np.float32).reshape(len(rows), -1)
            sims = mat @ q_vec
            best_idx = int(np.argmax(sims))
            if sims[best_idx] >= DUPLICATE_THRESHOLD:
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
                        db.execute(
                            "UPDATE insight SET content=?, embedding=?, last_used=? WHERE name=?",
                            (content, to_blob(new_emb), now, match_name)
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
            db.execute(
                "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                (name, content, emb_blob, initial_effectiveness, 0, now, tags_json)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{_utcnow().strftime('%H%M%S')}"
                db.execute(
                    "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                    (name, content, emb_blob, initial_effectiveness, 0, now, tags_json)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def recall(query: str, limit: int = 5, min_effectiveness: float = 0.0,
           min_relevance: float = MIN_RELEVANCE_DEFAULT,
           suppress_names: List[str] = None) -> List[dict]:
    """Recall insights by semantic similarity.

    Args:
        query: Search query
        limit: Maximum results
        min_effectiveness: Minimum effectiveness threshold
        min_relevance: Minimum cosine similarity (0.35 default). "No memory" beats "wrong memory."

    Returns list with _relevance, _score fields.
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
    q_vec = np.array(q_emb, dtype=np.float32)
    mat = np.frombuffer(b''.join(r["embedding"] for r in candidates),
                        dtype=np.float32).reshape(len(candidates), -1)
    similarities = mat @ q_vec

    # Score and filter by min_relevance
    scored = []
    w_rel, w_eff = SCORE_WEIGHTS['relevance'], SCORE_WEIGHTS['effectiveness']
    for i, r in enumerate(candidates):
        rel = float(similarities[i])
        if rel < min_relevance:
            continue
        eff = _causal_adjusted_effectiveness(r)
        scored.append((w_rel * rel + w_eff * eff, rel, eff, i))

    scored.sort(key=lambda x: -x[0])
    top = scored[:limit]

    if not top:
        return []

    # Build results from already-fetched full rows (O(1) index lookup)
    results = []
    for score, rel, eff, idx in top:
        row = candidates[idx]
        m = _to_dict(row)
        m["_relevance"] = round(rel, 3)
        m["_effectiveness"] = round(eff, 3)
        m["_score"] = round(score, 3)
        results.append(m)

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

    all_remove = to_remove + orphan_names
    with write_lock():
        if all_remove:
            placeholders = ",".join("?" for _ in all_remove)
            db.execute(f"DELETE FROM insight WHERE name IN ({placeholders})", all_remove)
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]
    return {
        "pruned": len(to_remove),
        "orphans_cleaned": len(orphan_names),
        "remaining": remaining,
        "removed": to_remove + orphan_names
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

    by_tag = {}

    loop_closed = total > 0 and with_feedback > 0
    issues = []
    if total == 0:
        issues.append("No insights yet")
    elif with_feedback == 0:
        issues.append("No feedback recorded - learning loop not closed")

    return {
        "status": "HEALTHY" if loop_closed and not issues else "NEEDS_ATTENTION",
        "total_insights": total,
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
                   suppress_names=suppress)
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

    if args.verbose and r is not None:
        cmd_args = {k: v for k, v in vars(args).items() if k not in ('cmd', 'verbose', 'db')}
        _log_verbose(args.cmd, cmd_args, r)

    print(json.dumps(r, indent=2))
