"""Tests for observability stats module."""
import pytest


def _insert_insight(db, name, effectiveness=0.5, use_count=0, recent_uses=0, context_spread=None):
    db.execute(
        "INSERT INTO insight (name, content, effectiveness, use_count, recent_uses, "
        "causal_hits, created_at, tags, context_spread) "
        "VALUES (?, ?, ?, ?, ?, 0, '2026-01-01T00:00:00', '[]', ?)",
        (name, f"content for {name}", effectiveness, use_count, recent_uses, context_spread)
    )
    db.commit()


class TestEffectivenessDistribution:
    def test_empty_db(self, test_db):
        from lib.memory.stats import effectiveness_distribution
        result = effectiveness_distribution()
        assert len(result) == 10
        assert all(r["count"] == 0 for r in result)

    def test_with_data(self, test_db):
        from lib.memory.stats import effectiveness_distribution
        _insert_insight(test_db, "low", effectiveness=0.2, use_count=1)
        _insert_insight(test_db, "mid", effectiveness=0.5, use_count=1)
        _insert_insight(test_db, "high", effectiveness=0.8, use_count=1)
        result = effectiveness_distribution()
        total = sum(r["count"] for r in result)
        assert total == 3


class TestContextSpreadDistribution:
    def test_empty(self, test_db):
        from lib.memory.stats import context_spread_distribution
        result = context_spread_distribution()
        assert len(result) == 5

    def test_with_spread_data(self, test_db):
        from lib.memory.stats import context_spread_distribution
        _insert_insight(test_db, "narrow", context_spread=0.02, use_count=1)
        _insert_insight(test_db, "wide", context_spread=0.25, use_count=1)
        result = context_spread_distribution()
        total = sum(r["count"] for r in result)
        assert total == 2


class TestVelocity:
    def test_velocity_distribution(self, test_db):
        from lib.memory.stats import velocity_distribution
        _insert_insight(test_db, "active", recent_uses=3, use_count=5)
        _insert_insight(test_db, "idle", recent_uses=0, use_count=2)
        result = velocity_distribution()
        assert len(result) >= 1

    def test_top_velocity(self, test_db):
        from lib.memory.stats import top_velocity
        _insert_insight(test_db, "hot", recent_uses=5, use_count=10)
        _insert_insight(test_db, "warm", recent_uses=2, use_count=5)
        result = top_velocity(limit=2)
        assert len(result) == 2
        assert result[0]["name"] == "hot"


class TestTopConnected:
    def test_with_edges(self, test_db):
        from lib.memory.stats import top_connected
        _insert_insight(test_db, "hub")
        _insert_insight(test_db, "spoke1")
        _insert_insight(test_db, "spoke2")
        hub_id = test_db.execute("SELECT id FROM insight WHERE name='hub'").fetchone()["id"]
        s1_id = test_db.execute("SELECT id FROM insight WHERE name='spoke1'").fetchone()["id"]
        s2_id = test_db.execute("SELECT id FROM insight WHERE name='spoke2'").fetchone()["id"]
        test_db.execute(
            "INSERT INTO insight_edges (src_id, dst_id, weight, relation, created_at) VALUES (?, ?, 0.7, 'similar', '2026-01-01')",
            (min(hub_id, s1_id), max(hub_id, s1_id))
        )
        test_db.execute(
            "INSERT INTO insight_edges (src_id, dst_id, weight, relation, created_at) VALUES (?, ?, 0.7, 'similar', '2026-01-01')",
            (min(hub_id, s2_id), max(hub_id, s2_id))
        )
        test_db.commit()
        result = top_connected(limit=1)
        assert len(result) == 1
        assert result[0]["name"] == "hub"
        assert result[0]["degree"] == 2


class TestSessionLogSummary:
    def test_with_entries(self, test_db):
        from lib.memory.stats import session_log_summary
        test_db.execute(
            "INSERT INTO session_log (agent_id, agent_type, outcome, summary, transcript_hash, created_at) "
            "VALUES ('a1', 'builder', 'delivered', 'built it', 'h1', '2026-03-12T00:00:00')"
        )
        test_db.execute(
            "INSERT INTO session_log (agent_id, agent_type, outcome, summary, transcript_hash, created_at) "
            "VALUES ('a2', 'builder', 'blocked', 'failed', 'h2', '2026-03-12T00:00:00')"
        )
        test_db.commit()
        result = session_log_summary(days=30)
        assert result["total"] == 2
        assert result["by_outcome"]["delivered"] == 1
        assert result["by_outcome"]["blocked"] == 1


class TestFullStats:
    def test_all_keys_present(self, test_db):
        from lib.memory.stats import full_stats
        result = full_stats()
        assert "effectiveness" in result
        assert "context_spread" in result
        assert "velocity" in result
        assert "top_velocity" in result
        assert "top_connected" in result
        assert "session_log" in result
