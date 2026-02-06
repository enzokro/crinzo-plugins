#!/usr/bin/env python3
"""Memory: unified insight storage and retrieval.

Core API (6 primitives):
- store(content, tags) -> {"status": "added"|"merged", "name": str}
- recall(query, limit) -> insights sorted by relevance × effectiveness × recency
- feedback(names, outcome) -> update effectiveness
- decay(unused_days) -> decay dormant insights
- prune(min_effectiveness, min_uses) -> remove low-performing insights
- health() -> system status

Scoring formula:
    score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
    recency = 2^(-days_since_use / 14)
"""

import json
import math
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List

# Constants
SCORE_WEIGHTS = {'relevance': 0.5, 'effectiveness': 0.3, 'recency': 0.2}
DECAY_HALF_LIFE = 14  # days
DUPLICATE_THRESHOLD = 0.85
MIN_RELEVANCE_DEFAULT = 0.35  # MiniLM-L6-v2: unrelated 0.05-0.25, related 0.35+
CAUSAL_SIMILARITY_THRESHOLD = 0.25  # For feedback attribution filtering

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
    """Create kebab-case slug from text."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:50] if len(s) > 50 else s


def _effectiveness(row) -> float:
    """Get effectiveness from row (already stored as 0-1)."""
    return row["effectiveness"] if row["effectiveness"] is not None else 0.5


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
        return math.pow(2, -days_ago / DECAY_HALF_LIFE)
    except Exception:
        return 0.5


def _to_dict(row) -> dict:
    """Convert database row to insight dict."""
    tags = []
    if row["tags"]:
        try:
            tags = json.loads(row["tags"])
        except Exception:
            pass

    d = {
        "name": row["name"],
        "content": row["content"],
        "effectiveness": round(_effectiveness(row), 3),
        "use_count": row["use_count"] or 0,
        "created_at": row["created_at"],
        "last_used": row["last_used"],
        "tags": tags
    }

    # Include causal_hits if column exists
    try:
        d["causal_hits"] = row["causal_hits"] or 0
    except (IndexError, KeyError):
        d["causal_hits"] = 0

    return d


# =============================================================================
# CORE PRIMITIVES
# =============================================================================

def store(content: str, tags: list = None) -> dict:
    """Store an insight.

    Args:
        content: "When X, do Y because Z" format
        tags: Optional list of tags

    Returns: {"status": "added"|"merged", "name": str, "reason": str}
    """
    if not content or len(content.strip()) < 20:
        return {"status": "rejected", "name": "", "reason": "content too short (min 20 chars)"}

    content = content.strip()
    tags = tags or []

    # Check for semantic duplicate
    new_emb = embed(content)
    if new_emb:
        db = get_db()
        for row in db.execute("SELECT name, embedding FROM insight WHERE embedding IS NOT NULL"):
            if row["embedding"] and cosine(new_emb, from_blob(row["embedding"])) >= DUPLICATE_THRESHOLD:
                # Update use count on merge
                with write_lock():
                    db.execute(
                        "UPDATE insight SET use_count = use_count + 1, last_used = ? WHERE name = ?",
                        (datetime.now().isoformat(), row["name"])
                    )
                    db.commit()
                return {"status": "merged", "name": row["name"], "reason": "similar exists"}

    name = _slug(content[:50])
    if not name:
        name = f"insight-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    emb_blob = to_blob(new_emb) if new_emb else None
    tags_json = json.dumps(tags)

    db = get_db()
    now = datetime.now().isoformat()

    with write_lock():
        try:
            db.execute(
                "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                (name, content, emb_blob, 0.5, 0, now, tags_json)
            )
            db.commit()
            return {"status": "added", "name": name, "reason": ""}
        except Exception as e:
            if "UNIQUE" in str(e):
                name = f"{name}-{datetime.now().strftime('%H%M%S')}"
                db.execute(
                    "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) VALUES (?,?,?,?,?,?,?)",
                    (name, content, emb_blob, 0.5, 0, now, tags_json)
                )
                db.commit()
                return {"status": "added", "name": name, "reason": ""}
            raise


def recall(query: str, limit: int = 5, min_effectiveness: float = 0.0,
           min_relevance: float = MIN_RELEVANCE_DEFAULT) -> List[dict]:
    """Recall insights by semantic similarity.

    Args:
        query: Search query
        limit: Maximum results
        min_effectiveness: Minimum effectiveness threshold
        min_relevance: Minimum cosine similarity (0.35 default). "No memory" beats "wrong memory."

    Returns list with _relevance, _recency, _score fields.
    """
    db = get_db()
    rows = db.execute("SELECT * FROM insight WHERE embedding IS NOT NULL").fetchall()
    if not rows:
        return []

    q_emb = embed(query)
    if q_emb is None:
        # Fallback: by effectiveness only
        rows = db.execute(
            "SELECT * FROM insight ORDER BY effectiveness DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [_to_dict(r) for r in rows]

    scored = []
    for r in rows:
        eff = _effectiveness(r)
        if eff < min_effectiveness:
            continue

        rel = cosine(q_emb, from_blob(r["embedding"]))

        # Relevance gate: skip insights below threshold
        if rel < min_relevance:
            continue

        rec = _recency_score(r["last_used"], r["created_at"])

        score = (SCORE_WEIGHTS['relevance'] * rel) + \
                (SCORE_WEIGHTS['effectiveness'] * eff) + \
                (SCORE_WEIGHTS['recency'] * rec)

        m = _to_dict(r)
        m["_relevance"] = round(rel, 3)
        m["_recency"] = round(rec, 3)
        m["_score"] = round(score, 3)
        scored.append((score, m))

    scored.sort(key=lambda x: -x[0])
    return [m for _, m in scored[:limit]]


def get(name: str) -> Optional[dict]:
    """Get specific insight by name."""
    db = get_db()
    row = db.execute("SELECT * FROM insight WHERE name=?", (name,)).fetchone()
    return _to_dict(row) if row else None


def feedback(names: List[str], outcome: str, causal_names: List[str] = None) -> dict:
    """Update effectiveness based on outcome with causal filtering.

    Args:
        names: Insight names that were injected
        outcome: "delivered" or "blocked"
        causal_names: Subset of names that passed causal similarity check.
                      None means treat all as causal (backward compatible).

    Causal insights get standard EMA update.
    Non-causal insights erode 4% toward neutral (0.5), breaking rich-get-richer cycles.

    Returns count of updated insights with causal breakdown.
    """
    if outcome not in ("delivered", "blocked"):
        return {"updated": 0, "error": "outcome must be 'delivered' or 'blocked'"}

    db = get_db()
    now = datetime.now().isoformat()
    updated = 0
    causal_count = 0
    eroded_count = 0

    causal_set = set(causal_names) if causal_names is not None else None
    outcome_value = 1.0 if outcome == "delivered" else 0.0

    with write_lock():
        for name in set(names):
            row = db.execute("SELECT effectiveness, use_count FROM insight WHERE name=?", (name,)).fetchone()
            if not row:
                continue

            old_eff = row["effectiveness"] or 0.5
            is_causal = causal_set is None or name in causal_set

            if is_causal:
                # Standard EMA update for causally relevant insights
                new_eff = old_eff * 0.9 + outcome_value * 0.1
                new_eff = max(0.0, min(1.0, new_eff))
                db.execute(
                    "UPDATE insight SET effectiveness=?, use_count=use_count+1, "
                    "causal_hits=causal_hits+1, last_used=? WHERE name=?",
                    (new_eff, now, name)
                )
                causal_count += 1
            else:
                # Erode toward neutral: 4% toward 0.5
                new_eff = old_eff + (0.5 - old_eff) * 0.04
                new_eff = max(0.0, min(1.0, new_eff))
                db.execute(
                    "UPDATE insight SET effectiveness=?, use_count=use_count+1, "
                    "last_used=? WHERE name=?",
                    (new_eff, now, name)
                )
                eroded_count += 1

            updated += 1
        db.commit()

    return {
        "updated": updated,
        "outcome": outcome,
        "names": list(set(names)),
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
    cutoff = (datetime.now() - timedelta(days=unused_days)).isoformat()

    with write_lock():
        # Move effectiveness toward 0.5 by 10%
        cursor = db.execute("""
            UPDATE insight
            SET effectiveness = effectiveness * 0.9 + 0.5 * 0.1
            WHERE (last_used IS NULL OR last_used < ?)
        """, (cutoff,))
        db.commit()
        affected = cursor.rowcount

    return {"decayed": affected, "threshold_days": unused_days}


def prune(min_effectiveness: float = 0.25, min_uses: int = 3) -> dict:
    """Remove insights that have proven unhelpful.

    Only prunes insights with at least min_uses to ensure fair evaluation.
    """
    db = get_db()
    rows = db.execute(
        "SELECT name, effectiveness, use_count FROM insight WHERE use_count >= ?",
        (min_uses,)
    ).fetchall()

    to_remove = []
    for r in rows:
        if r["effectiveness"] < min_effectiveness:
            to_remove.append(r["name"])

    with write_lock():
        for n in to_remove:
            db.execute("DELETE FROM insight WHERE name=?", (n,))
        db.commit()

    remaining = db.execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]
    return {"pruned": len(to_remove), "remaining": remaining, "removed": to_remove}


def health() -> dict:
    """Check learning system health."""
    db = get_db()

    total = db.execute("SELECT COUNT(*) as c FROM insight").fetchone()["c"]

    # Get tag distribution
    by_tag = {}
    for row in db.execute("SELECT tags FROM insight"):
        try:
            tags = json.loads(row["tags"]) if row["tags"] else []
            for tag in tags:
                by_tag[tag] = by_tag.get(tag, 0) + 1
        except Exception:
            pass

    with_feedback = db.execute("SELECT COUNT(*) as c FROM insight WHERE use_count > 0").fetchone()["c"]

    # Average effectiveness
    avg_eff_row = db.execute("SELECT AVG(effectiveness) as avg_eff FROM insight WHERE use_count > 0").fetchone()
    avg_eff = avg_eff_row["avg_eff"] if avg_eff_row and avg_eff_row["avg_eff"] else 0.5

    # Causal ratio: what fraction of feedback is causally attributed
    try:
        causal_row = db.execute(
            "SELECT SUM(causal_hits) as ch, SUM(use_count) as uc FROM insight WHERE use_count > 0"
        ).fetchone()
        total_causal = causal_row["ch"] or 0
        total_uses = causal_row["uc"] or 0
        causal_ratio = round(total_causal / total_uses, 3) if total_uses > 0 else 0.0
    except Exception:
        causal_ratio = 0.0

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
        "causal_ratio": causal_ratio,
        "issues": issues
    }


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

    s = sub.add_parser("get")
    s.add_argument("name")

    s = sub.add_parser("feedback")
    s.add_argument("--names", required=True, help="JSON list of insight names")
    s.add_argument("--outcome", required=True, choices=["delivered", "blocked"])
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
        r = recall(args.query, args.limit, args.min_effectiveness, args.min_relevance)
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
