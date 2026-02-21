"""Tests for strategic_recall() — broad recall with summary for orchestrator RECALL phase.

Uses test_db + mock_embeddings fixtures (fast, deterministic).
"""

import json
import pytest
from lib.injection import (
    strategic_recall,
    STRATEGIC_RECALL_LIMIT,
    STRATEGIC_MIN_RELEVANCE,
    STRATEGIC_HIGH_EFFECTIVENESS,
    STRATEGIC_LOW_EFFECTIVENESS,
)
from lib.memory.core import store, feedback


# =============================================================================
# Structure
# =============================================================================

class TestStrategicRecallStructure:
    """Return shape validation."""

    def test_returns_insights_and_summary(self, test_db, mock_embeddings):
        store(content="When testing APIs, mock at service boundary for better isolation",
              tags=["testing"])
        result = strategic_recall("testing patterns")
        assert "insights" in result
        assert "summary" in result
        assert isinstance(result["insights"], list)
        assert isinstance(result["summary"], dict)

    def test_summary_fields_present(self, test_db, mock_embeddings):
        store(content="When deploying services, use health checks to verify readiness",
              tags=["deployment"])
        result = strategic_recall("deployment")
        summary = result["summary"]
        expected_fields = [
            "total_recalled", "total_in_system", "avg_relevance",
            "avg_effectiveness", "proven_count", "risky_count",
            "untested_count", "tag_distribution", "coverage_ratio",
        ]
        for field in expected_fields:
            assert field in summary, f"Missing summary field: {field}"

    def test_empty_db_returns_zero_summary(self, test_db, mock_embeddings):
        result = strategic_recall("anything")
        assert result["insights"] == []
        summary = result["summary"]
        assert summary["total_recalled"] == 0
        assert summary["total_in_system"] == 0
        assert summary["avg_relevance"] == 0.0
        assert summary["avg_effectiveness"] == 0.0
        assert summary["proven_count"] == 0
        assert summary["risky_count"] == 0
        assert summary["untested_count"] == 0
        assert summary["tag_distribution"] == {}
        assert summary["coverage_ratio"] == 0.0

    def test_insight_dict_has_expected_keys(self, test_db, mock_embeddings):
        store(content="When writing migrations, always add rollback steps for safety",
              tags=["database", "migrations"])
        result = strategic_recall("database migrations")
        if result["insights"]:
            insight = result["insights"][0]
            assert "name" in insight
            assert "content" in insight
            assert "effectiveness" in insight
            assert "use_count" in insight
            assert "causal_hits" in insight
            assert "tags" in insight
            assert "_relevance" in insight
            assert "_effectiveness" in insight
            assert "_score" in insight


# =============================================================================
# Tags
# =============================================================================

class TestStrategicRecallTags:
    """Tag enrichment from database."""

    def test_insights_include_tags(self, test_db, mock_embeddings):
        store(content="When configuring auth tokens, use short expiry for security",
              tags=["auth", "security"])
        result = strategic_recall("auth configuration")
        if result["insights"]:
            # At least one insight should have tags populated
            tagged = [m for m in result["insights"] if m["tags"]]
            assert len(tagged) > 0

    def test_tag_distribution_counts(self, test_db, mock_embeddings):
        store(content="When testing auth flows, mock the token provider for isolation",
              tags=["testing", "auth"])
        store(content="When testing database queries, use fixtures for reproducibility",
              tags=["testing", "database"])
        store(content="When securing endpoints, validate all input parameters carefully",
              tags=["auth", "security"])
        result = strategic_recall("testing and auth patterns")
        summary = result["summary"]
        tag_dist = summary["tag_distribution"]
        # Tags from recalled insights should be counted
        if result["insights"]:
            # Manually verify: count tags across returned insights
            expected = {}
            for m in result["insights"]:
                for tag in m.get("tags", []):
                    expected[tag] = expected.get(tag, 0) + 1
            assert tag_dist == expected

    def test_empty_tags_handled(self, test_db, mock_embeddings):
        store(content="When handling errors, always log the full stack trace for debugging",
              tags=[])
        result = strategic_recall("error handling")
        # Should not crash; tags should be empty list
        for m in result["insights"]:
            assert isinstance(m["tags"], list)


# =============================================================================
# Parameters
# =============================================================================

class TestStrategicRecallParameters:
    """Limit and relevance parameters."""

    def test_respects_limit(self, test_db, mock_embeddings):
        # Store more insights than the limit
        for i in range(5):
            store(content=f"When handling scenario {i}, apply pattern {i} because reason {i}",
                  tags=[f"tag-{i}"])
        result = strategic_recall("scenario handling", limit=2)
        assert len(result["insights"]) <= 2

    def test_default_limit_is_strategic(self):
        assert STRATEGIC_RECALL_LIMIT == 15

    def test_default_min_relevance_below_tactical(self):
        # Strategic gate (0.30) is wider than tactical (0.35)
        from lib.memory.core import MIN_RELEVANCE_DEFAULT
        assert STRATEGIC_MIN_RELEVANCE < MIN_RELEVANCE_DEFAULT

    def test_constants_are_sensible(self):
        assert STRATEGIC_HIGH_EFFECTIVENESS == 0.70
        assert STRATEGIC_LOW_EFFECTIVENESS == 0.40
        assert STRATEGIC_HIGH_EFFECTIVENESS > STRATEGIC_LOW_EFFECTIVENESS


# =============================================================================
# Summary Statistics
# =============================================================================

class TestStrategicRecallSummaryStats:
    """Computed summary statistics."""

    def test_coverage_ratio_computation(self, test_db, mock_embeddings):
        # Store semantically distinct insights (avoid dedup)
        store(content="When deploying containers, use health check endpoints for liveness probes",
              tags=["deployment"])
        store(content="When writing SQL migrations, always include rollback scripts for safety",
              tags=["database"])
        store(content="When configuring authentication, rotate JWT signing keys on a schedule",
              tags=["auth"])
        store(content="When profiling memory usage, check for unclosed file handles and leaks",
              tags=["debugging"])
        result = strategic_recall("deployment and infrastructure")
        summary = result["summary"]
        total = summary["total_in_system"]
        recalled = summary["total_recalled"]
        assert total == 4
        if recalled > 0:
            expected_ratio = round(recalled / total, 3)
            assert summary["coverage_ratio"] == expected_ratio

    def test_proven_count_threshold(self, test_db, mock_embeddings):
        """Insights with effectiveness >= 0.70 count as proven."""
        r = store(content="When deploying to production, always run smoke tests first for safety",
                  tags=["deployment"])
        name = r["name"]
        # Drive effectiveness up with repeated delivered feedback
        for _ in range(8):
            feedback([name], "delivered", causal_names=[name])
        result = strategic_recall("deployment patterns")
        # Find our insight
        matching = [m for m in result["insights"] if m["name"] == name]
        if matching:
            # After 8 delivered feedbacks from 0.5: should be well above 0.70
            assert matching[0]["_effectiveness"] >= STRATEGIC_HIGH_EFFECTIVENESS
            assert result["summary"]["proven_count"] >= 1

    def test_risky_count_threshold(self, test_db, mock_embeddings):
        """Insights with effectiveness < 0.40 count as risky."""
        r = store(content="When integrating payment gateways, use synchronous calls for simplicity",
                  tags=["payments"])
        name = r["name"]
        # Drive effectiveness down with repeated blocked feedback
        for _ in range(8):
            feedback([name], "blocked", causal_names=[name])
        result = strategic_recall("payment integration")
        matching = [m for m in result["insights"] if m["name"] == name]
        if matching:
            assert matching[0]["_effectiveness"] < STRATEGIC_LOW_EFFECTIVENESS
            assert result["summary"]["risky_count"] >= 1

    def test_untested_count(self, test_db, mock_embeddings):
        """Insights with use_count < 3 count as untested."""
        store(content="When writing parsers, use recursive descent for clarity and debuggability",
              tags=["parsing"])
        result = strategic_recall("parser patterns")
        if result["insights"]:
            # Fresh insight: use_count=0 < 3, should be untested
            assert result["summary"]["untested_count"] >= 1

    def test_avg_relevance_is_mean(self, test_db, mock_embeddings):
        store(content="When optimizing queries, add composite indexes on frequently joined columns",
              tags=["database"])
        store(content="When caching results, set TTL based on data volatility for freshness",
              tags=["caching"])
        result = strategic_recall("database optimization")
        if len(result["insights"]) > 0:
            relevances = [m["_relevance"] for m in result["insights"]]
            expected = round(sum(relevances) / len(relevances), 3)
            assert result["summary"]["avg_relevance"] == expected

    def test_avg_effectiveness_is_mean(self, test_db, mock_embeddings):
        store(content="When designing APIs, version endpoints from day one for compatibility",
              tags=["api"])
        result = strategic_recall("API design")
        if len(result["insights"]) > 0:
            effs = [m.get("_effectiveness", m.get("effectiveness", 0.5))
                    for m in result["insights"]]
            expected = round(sum(effs) / len(effs), 3)
            assert result["summary"]["avg_effectiveness"] == expected


# =============================================================================
# CLI integration (via subprocess would be slow; test function directly)
# =============================================================================

class TestStrategicRecallCLI:
    """CLI subcommand wiring."""

    def test_strategic_recall_json_serializable(self, test_db, mock_embeddings):
        """Result must be JSON-serializable for CLI output."""
        store(content="When debugging memory leaks, check for unclosed file handles first",
              tags=["debugging"])
        result = strategic_recall("debugging patterns")
        # Should not raise
        serialized = json.dumps(result, indent=2)
        parsed = json.loads(serialized)
        assert "insights" in parsed
        assert "summary" in parsed
