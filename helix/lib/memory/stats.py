"""Observability for tuning constants.

Read-only diagnostics: effectiveness distribution, context_spread distribution,
velocity distribution, graph degree, session_log summary.
Used by CLI `stats` subcommand and helix-stats skill.
"""

try:
    from ..db.connection import get_db
except ImportError:
    from db.connection import get_db


def effectiveness_distribution(buckets=10):
    """Histogram of effectiveness values for insights with use_count > 0."""
    db = get_db()
    rows = db.execute(
        "SELECT effectiveness FROM insight WHERE use_count > 0"
    ).fetchall()
    if not rows:
        return [{"range": f"{i/buckets:.1f}-{(i+1)/buckets:.1f}", "count": 0}
                for i in range(buckets)]
    result = []
    for i in range(buckets):
        low = i / buckets
        high = (i + 1) / buckets
        count = sum(1 for r in rows if low <= (r["effectiveness"] or 0) < high)
        result.append({"range": f"{low:.1f}-{high:.1f}", "count": count})
    return result


def context_spread_distribution(buckets=5):
    """Histogram of context_spread for insights where spread is not NULL."""
    db = get_db()
    rows = db.execute(
        "SELECT context_spread FROM insight WHERE context_spread IS NOT NULL"
    ).fetchall()
    if not rows:
        return [{"range": f"{i*0.1:.1f}-{(i+1)*0.1:.1f}", "count": 0}
                for i in range(buckets)]
    max_spread = max(r["context_spread"] for r in rows) or 0.5
    bucket_size = max(0.01, max_spread / buckets)
    result = []
    for i in range(buckets):
        low = i * bucket_size
        high = (i + 1) * bucket_size
        if i == buckets - 1:
            # Last bucket includes upper bound
            count = sum(1 for r in rows if low <= (r["context_spread"] or 0) <= high)
        else:
            count = sum(1 for r in rows if low <= (r["context_spread"] or 0) < high)
        result.append({"range": f"{low:.3f}-{high:.3f}", "count": count})
    return result


def velocity_distribution():
    """Count of insights by recent_uses value."""
    db = get_db()
    rows = db.execute(
        "SELECT recent_uses, COUNT(*) as cnt FROM insight GROUP BY recent_uses ORDER BY recent_uses"
    ).fetchall()
    return [{"recent_uses": r["recent_uses"] or 0, "count": r["cnt"]} for r in rows]


def top_velocity(limit=5):
    """Insights with highest recent_uses."""
    db = get_db()
    rows = db.execute(
        "SELECT name, recent_uses, effectiveness, last_feedback_at "
        "FROM insight WHERE recent_uses > 0 ORDER BY recent_uses DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"name": r["name"], "recent_uses": r["recent_uses"],
             "effectiveness": round(r["effectiveness"] or 0.5, 3),
             "last_feedback_at": r["last_feedback_at"]} for r in rows]


def top_connected(limit=5):
    """Insights with most graph edges (highest degree)."""
    db = get_db()
    rows = db.execute(
        "SELECT i.name, COUNT(*) as degree "
        "FROM insight i "
        "JOIN insight_edges e ON (e.src_id = i.id OR e.dst_id = i.id) "
        "GROUP BY i.id "
        "ORDER BY degree DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return [{"name": r["name"], "degree": r["degree"]} for r in rows]


def session_log_summary(days=30):
    """Outcome counts from session_log in the last N days."""
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat()
    rows = db.execute(
        "SELECT outcome, agent_type, COUNT(*) as cnt FROM session_log "
        "WHERE created_at > ? GROUP BY outcome, agent_type",
        (cutoff,)
    ).fetchall()
    by_outcome = {}
    by_agent_type = {}
    total = 0
    for r in rows:
        outcome = r["outcome"] or "unknown"
        agent_type = r["agent_type"] or "unknown"
        cnt = r["cnt"]
        by_outcome[outcome] = by_outcome.get(outcome, 0) + cnt
        by_agent_type[agent_type] = by_agent_type.get(agent_type, 0) + cnt
        total += cnt
    return {"total": total, "by_outcome": by_outcome, "by_agent_type": by_agent_type}


def full_stats():
    """Composite statistics for calibration."""
    return {
        "effectiveness": effectiveness_distribution(),
        "context_spread": context_spread_distribution(),
        "velocity": velocity_distribution(),
        "top_velocity": top_velocity(),
        "top_connected": top_connected(),
        "session_log": session_log_summary(),
    }
