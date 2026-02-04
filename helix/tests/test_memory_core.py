"""Tests for memory/core.py - unified insight storage.

Critical path: The memory feedback loop is the core learning mechanism.
These tests verify store/recall/feedback work correctly with the new unified API.
"""

import pytest
from datetime import datetime, timedelta


class TestStore:
    """Tests for insight storage and validation."""

    def test_store_valid_insight(self, test_db, mock_embeddings):
        """Store insight successfully."""
        from lib.memory.core import store, get

        result = store(
            content="When debugging Python imports, check sys.path first because module resolution depends on it",
            tags=["python", "debugging"]
        )

        assert result["status"] == "added"
        assert result["name"]  # Non-empty slug generated
        assert result["reason"] == ""

        # Verify persisted
        insight = get(result["name"])
        assert insight is not None
        assert "sys.path" in insight["content"]
        assert "python" in insight["tags"]

    def test_store_rejects_short_content(self, test_db):
        """Reject content shorter than 20 characters."""
        from lib.memory.core import store

        result = store(content="too short")

        assert result["status"] == "rejected"
        assert "too short" in result["reason"]

    def test_store_deduplicates_similar(self, test_db, mock_embeddings):
        """Similar insights (cosine >= 0.85) are merged, not duplicated."""
        from lib.memory.core import store

        # Store first insight
        result1 = store(
            content="When debugging Python imports, check sys.path first because module resolution depends on it"
        )
        assert result1["status"] == "added"

        # Attempt to store nearly identical insight
        result2 = store(
            content="When debugging Python imports, check sys.path first because module resolution depends on it"
        )

        assert result2["status"] == "merged"
        assert result2["name"] == result1["name"]

    def test_store_with_tags(self, test_db, mock_embeddings):
        """Tags are stored correctly."""
        from lib.memory.core import store, get

        result = store(
            content="When implementing auth, use JWT with short expiry because it limits damage from stolen tokens",
            tags=["security", "auth", "jwt"]
        )

        insight = get(result["name"])
        assert "security" in insight["tags"]
        assert "auth" in insight["tags"]


class TestRecall:
    """Tests for insight recall and ranking."""

    def test_recall_ranks_by_score(self, test_db, mock_embeddings):
        """Recall returns insights ranked by composite score."""
        from lib.memory.core import store, recall

        # Store some insights
        store(content="When implementing auth, use JWT with refresh tokens for better security")
        store(content="When debugging Python imports, check sys.path first")
        store(content="When writing tests, mock at service boundaries not HTTP level")

        results = recall("authentication and JWT implementation", limit=5)

        assert len(results) > 0
        # All results should have score fields
        for r in results:
            assert "_relevance" in r
            assert "_recency" in r
            assert "_score" in r

        # Results should be sorted by score descending
        scores = [r["_score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_recall_filters_by_effectiveness(self, test_db, mock_embeddings):
        """Recall respects min_effectiveness threshold."""
        from lib.memory.core import store, recall, feedback

        # Store insight and give it feedback
        result = store(
            content="When handling async errors, always wrap in try/catch because unhandled rejections crash Node"
        )

        # Give positive feedback to increase effectiveness
        feedback([result["name"]], "delivered")
        feedback([result["name"]], "delivered")

        # Should appear with low threshold
        results_low = recall("async error handling", min_effectiveness=0.0, limit=5)
        names_low = [r["name"] for r in results_low]

        # The insight should be in results
        assert result["name"] in names_low


class TestFeedback:
    """Tests for feedback loop - THE critical mechanism."""

    def test_feedback_delivered_increases_effectiveness(self, test_db, mock_embeddings):
        """Delivered outcome increases effectiveness."""
        from lib.memory.core import store, get, feedback

        result = store(
            content="When connection times out, increase timeout and add retry with exponential backoff"
        )
        name = result["name"]

        # Check initial state
        insight_before = get(name)
        assert insight_before["effectiveness"] == 0.5  # Neutral start
        assert insight_before["use_count"] == 0

        # Give positive feedback
        fb_result = feedback([name], "delivered")

        assert fb_result["updated"] == 1
        assert fb_result["outcome"] == "delivered"

        # Check effectiveness increased
        insight_after = get(name)
        assert insight_after["effectiveness"] > insight_before["effectiveness"]
        assert insight_after["use_count"] == 1
        assert insight_after["last_used"] is not None

    def test_feedback_blocked_decreases_effectiveness(self, test_db, mock_embeddings):
        """Blocked outcome decreases effectiveness."""
        from lib.memory.core import store, get, feedback

        result = store(
            content="When memory leaks occur, check for unclosed event listeners"
        )
        name = result["name"]

        insight_before = get(name)

        # Give negative feedback
        fb_result = feedback([name], "blocked")

        assert fb_result["updated"] == 1

        insight_after = get(name)
        assert insight_after["effectiveness"] < insight_before["effectiveness"]
        assert insight_after["use_count"] == 1

    def test_feedback_skips_unknown_insights(self, test_db, mock_embeddings):
        """Non-existent insight names are silently skipped."""
        from lib.memory.core import feedback

        fb_result = feedback(["nonexistent-insight-name", "also-does-not-exist"], "delivered")

        assert fb_result["updated"] == 0

    def test_feedback_rejects_invalid_outcome(self, test_db, mock_embeddings):
        """Invalid outcome strings are rejected."""
        from lib.memory.core import store, feedback

        result = store(content="When testing async code, use proper async test utilities")

        fb_result = feedback([result["name"]], "invalid")

        assert fb_result["updated"] == 0
        assert "error" in fb_result


class TestDecay:
    """Tests for decay mechanism."""

    def test_decay_affects_unused_insights(self, test_db, mock_embeddings):
        """Decay moves unused insights toward neutral effectiveness."""
        from lib.memory.core import store, get, feedback, decay, get_db, write_lock
        from datetime import datetime, timedelta

        # Store insight and give it feedback
        result = store(content="When X happens, do Y because Z - this is test content")
        feedback([result["name"]], "delivered")
        feedback([result["name"]], "delivered")

        insight_before = get(result["name"])
        assert insight_before["effectiveness"] > 0.5

        # Manually backdate last_used
        db = get_db()
        old_date = (datetime.now() - timedelta(days=60)).isoformat()
        with write_lock():
            db.execute("UPDATE insight SET last_used=? WHERE name=?", (old_date, result["name"]))
            db.commit()

        # Run decay
        decay_result = decay(unused_days=30)
        assert decay_result["decayed"] >= 1

        # Effectiveness should have moved toward 0.5
        insight_after = get(result["name"])
        assert insight_after["effectiveness"] < insight_before["effectiveness"]


class TestPrune:
    """Tests for pruning low-performing insights."""

    def test_prune_removes_low_effectiveness(self, test_db, mock_embeddings):
        """Prune removes insights below effectiveness threshold."""
        from lib.memory.core import store, get, feedback, prune

        # Store insight and make it fail repeatedly
        result = store(content="When A happens, do B - but this advice is bad")

        # Give negative feedback many times to drive effectiveness down
        # EMA: new_eff = old * 0.9 + 0 * 0.1, so need ~15 to get below 0.25
        for _ in range(15):
            feedback([result["name"]], "blocked")

        insight = get(result["name"])
        assert insight["effectiveness"] < 0.25
        assert insight["use_count"] >= 3

        # Run prune
        prune_result = prune(min_effectiveness=0.25, min_uses=3)
        assert result["name"] in prune_result["removed"]

        # Insight should be gone
        assert get(result["name"]) is None


class TestHealth:
    """Tests for health check."""

    def test_health_reports_status(self, test_db, mock_embeddings):
        """Health returns system status."""
        from lib.memory.core import store, feedback, health

        # Store and provide feedback
        result = store(content="When testing, mock at boundaries because it reduces coupling")
        feedback([result["name"]], "delivered")

        h = health()

        assert h["status"] in ("HEALTHY", "NEEDS_ATTENTION")
        assert h["total_insights"] >= 1
        assert h["with_feedback"] >= 1
        assert "effectiveness" in h
        assert isinstance(h["by_tag"], dict)

    def test_health_reports_no_insights(self, test_db):
        """Health reports when no insights exist."""
        from lib.memory.core import health

        h = health()

        assert h["status"] == "NEEDS_ATTENTION"
        assert "No insights" in h["issues"][0]
