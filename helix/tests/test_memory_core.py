"""Tests for memory/core.py - unified insight storage.

Critical path: The memory feedback loop is the core learning mechanism.
These tests verify store/recall/feedback work correctly with the new unified API.
"""

from datetime import timezone


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


class TestFeedbackMetrics:
    """Tests for last_feedback_at and recent_feedback."""

    def test_feedback_sets_last_feedback_at(self, test_db, mock_embeddings):
        """Causal feedback sets last_feedback_at timestamp."""
        from lib.memory.core import store, feedback, get_db

        result = store(
            content="When deploying services, always check health endpoints first because silent failures waste time"
        )
        name = result["name"]

        feedback([name], "delivered")

        db = get_db()
        row = db.execute("SELECT last_feedback_at FROM insight WHERE name=?", (name,)).fetchone()
        assert row["last_feedback_at"] is not None

    def test_health_includes_recent_feedback(self, test_db, mock_embeddings):
        """health() includes recent_feedback count."""
        from lib.memory.core import store, feedback, health

        result = store(
            content="When writing integration tests, use test containers because they match production"
        )
        feedback([result["name"]], "delivered")

        h = health()
        assert "recent_feedback" in h
        assert h["recent_feedback"] >= 1

    def test_feedback_plan_complete_treated_as_success(self, test_db, mock_embeddings):
        """plan_complete outcome increases effectiveness like delivered."""
        from lib.memory.core import store, get, feedback

        result = store(
            content="When planning microservices, separate by bounded context because it reduces coupling"
        )
        name = result["name"]
        before = get(name)["effectiveness"]

        feedback([name], "plan_complete")

        after = get(name)["effectiveness"]
        assert after > before


class TestRecallSuppressNames:
    """Tests for suppress_names parameter in recall."""

    def test_recall_suppress_names(self, test_db, mock_embeddings):
        """Suppressed names are excluded from recall results."""
        from lib.memory.core import store, recall

        r1 = store(content="When debugging Python imports, check sys.path first because module resolution depends on it")
        r2 = store(content="When handling async errors, always wrap in try/catch because unhandled rejections crash Node")

        # Recall without suppression
        all_results = recall("Python debugging imports", limit=10, min_relevance=0.0)
        all_names = [r["name"] for r in all_results]
        assert r1["name"] in all_names

        # Recall with suppression
        suppressed = recall("Python debugging imports", limit=10, min_relevance=0.0,
                           suppress_names=[r1["name"]])
        suppressed_names = [r["name"] for r in suppressed]
        assert r1["name"] not in suppressed_names


class TestCausalAdjustedEffectiveness:
    """Tests for _causal_adjusted_effectiveness read-time penalty."""

    def test_causal_adjusted_zero_causal(self):
        """High use, zero causal hits → floor multiplier (0.3)."""
        from lib.memory.core import _causal_adjusted_effectiveness

        row = {"effectiveness": 0.99, "use_count": 20, "causal_hits": 0}
        result = _causal_adjusted_effectiveness(row)
        assert abs(result - 0.99 * 0.3) < 0.001

    def test_causal_adjusted_full_causal(self):
        """All uses are causal → no penalty."""
        from lib.memory.core import _causal_adjusted_effectiveness

        row = {"effectiveness": 0.75, "use_count": 5, "causal_hits": 5}
        result = _causal_adjusted_effectiveness(row)
        assert abs(result - 0.75) < 0.001

    def test_causal_adjusted_low_use_count(self):
        """use_count < 3 → raw effectiveness unchanged."""
        from lib.memory.core import _causal_adjusted_effectiveness

        row = {"effectiveness": 0.99, "use_count": 2, "causal_hits": 0}
        result = _causal_adjusted_effectiveness(row)
        assert abs(result - 0.99) < 0.001

    def test_causal_adjusted_partial(self):
        """Partial causal ratio → proportional penalty."""
        from lib.memory.core import _causal_adjusted_effectiveness

        row = {"effectiveness": 0.80, "use_count": 10, "causal_hits": 5}
        result = _causal_adjusted_effectiveness(row)
        assert abs(result - 0.80 * 0.5) < 0.001


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

        # Manually backdate last_used (UTC to match core.py timestamps)
        db = get_db()
        old_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)).isoformat()
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

        # Give negative feedback to drive effectiveness down
        # EMA: new_eff = old * 0.8 + 0 * 0.2, so need ~6 to get below 0.25
        for _ in range(6):
            feedback([result["name"]], "blocked")

        insight = get(result["name"])
        assert insight["effectiveness"] < 0.25
        assert insight["use_count"] >= 3

        # Run prune
        prune_result = prune(min_effectiveness=0.25, min_uses=3)
        assert result["name"] in prune_result["removed"]

        # Insight should be gone
        assert get(result["name"]) is None


class TestMergeUseCount:
    """Tests for merge behavior on duplicate store."""

    def test_merge_does_not_increment_use_count(self, test_db, mock_embeddings):
        """Re-encountering an insight (dedup merge) should not increment use_count.

        A re-encounter is not a "use" — incrementing poisons the causal_hits/use_count ratio.
        """
        from lib.memory.core import store, get

        result1 = store(
            content="When debugging Python imports, check sys.path first because module resolution depends on it"
        )
        assert result1["status"] == "added"

        # Verify initial use_count is 0
        insight = get(result1["name"])
        assert insight["use_count"] == 0

        # Store duplicate — should merge
        result2 = store(
            content="When debugging Python imports, check sys.path first because module resolution depends on it"
        )
        assert result2["status"] == "merged"

        # use_count should still be 0
        insight_after = get(result1["name"])
        assert insight_after["use_count"] == 0


class TestMergeContentUpdate:
    """Tests for merge updating content when new version is better."""

    def test_merge_updates_content_when_longer(self, test_db, mock_embeddings):
        """Merge replaces content when new version is longer (better articulation)."""
        from lib.memory.core import store, get

        short = "When debugging Python imports, check sys.path first because it matters"
        long = "When debugging Python imports, check sys.path first because module resolution depends on it and virtual environments can shadow system packages"

        r1 = store(content=short)
        assert r1["status"] == "added"

        r2 = store(content=long)
        assert r2["status"] == "merged"
        assert r2["name"] == r1["name"]

        # Content should now be the longer version
        insight = get(r1["name"])
        assert insight["content"] == long

    def test_merge_updates_content_when_low_effectiveness(self, test_db, mock_embeddings):
        """Merge replaces content when existing insight has low effectiveness."""
        from lib.memory.core import store, get, feedback

        r1 = store(content="When debugging Python imports, check sys.path first because module resolution depends on it")
        name = r1["name"]

        # Drive effectiveness below 0.5
        for _ in range(5):
            feedback([name], "blocked")

        insight = get(name)
        assert insight["effectiveness"] < 0.5

        # Store same-length content — should update because low effectiveness
        r2 = store(content="When debugging Python imports, check sys.path first because module resolution depends on it")
        assert r2["status"] == "merged"

    def test_merge_preserves_content_when_shorter_and_effective(self, test_db, mock_embeddings):
        """Merge does NOT replace content when new version is shorter and existing is effective."""
        from lib.memory.core import store, get

        original = "When debugging Python imports, check sys.path first because module resolution depends on it"
        shorter = "When debugging Python imports check sys.path first because it matters"

        r1 = store(content=original)
        r2 = store(content=shorter)
        assert r2["status"] == "merged"

        # Content should be preserved (original was longer and effectiveness >= 0.5)
        insight = get(r1["name"])
        assert insight["content"] == original


class TestAsymmetricErosion:
    """Tests for asymmetric non-causal erosion."""

    def test_erosion_does_not_rehabilitate_bad_insights(self, test_db, mock_embeddings):
        """Below-0.5 effectiveness should NOT be pulled up by non-causal erosion.

        Bad insights stay bad until positive causal feedback proves otherwise.
        """
        from lib.memory.core import store, get, feedback

        result = store(
            content="When connection times out, just ignore it because timeouts resolve themselves"
        )
        name = result["name"]

        # Drive effectiveness below 0.5 with causal negative feedback
        for _ in range(10):
            feedback([name], "blocked")

        insight = get(name)
        assert insight["effectiveness"] < 0.5
        eff_before = insight["effectiveness"]

        # Now apply non-causal erosion (names present but not in causal_names)
        feedback([name], "delivered", causal_names=[])

        insight_after = get(name)
        # Below-0.5 insight should NOT have been pulled up
        assert insight_after["effectiveness"] == eff_before


class TestAsymmetricDecay:
    """Tests for asymmetric decay."""

    def test_decay_does_not_rehabilitate_bad_insights(self, test_db, mock_embeddings):
        """Below-0.5 effectiveness should NOT drift upward during decay."""
        from lib.memory.core import store, get, feedback, decay, get_db, write_lock
        from datetime import datetime, timedelta

        result = store(
            content="When X happens, do Y because Z - this advice turned out bad"
        )
        name = result["name"]

        # Drive below 0.5 with negative feedback
        for _ in range(10):
            feedback([name], "blocked")

        insight = get(name)
        assert insight["effectiveness"] < 0.5
        eff_before = insight["effectiveness"]

        # Backdate so decay applies
        db = get_db()
        old_date = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)).isoformat()
        with write_lock():
            db.execute("UPDATE insight SET last_used=? WHERE name=?", (old_date, name))
            db.commit()

        # Run decay
        decay(unused_days=30)

        insight_after = get(name)
        # Should NOT have moved toward 0.5 (upward)
        assert insight_after["effectiveness"] == eff_before


class TestCausalAdjustedPrune:
    """Tests for prune using causal-adjusted effectiveness."""

    def test_prune_uses_causal_adjusted_effectiveness(self, test_db, mock_embeddings):
        """Insight with raw eff 0.50 but low causal ratio gets pruned.

        use_count=20, causal_hits=0 → adjusted eff = 0.50 * 0.3 = 0.15 → below 0.25 → pruned.
        """
        from lib.memory.core import store, get, prune, get_db, write_lock

        result = store(
            content="When optimizing, use indexes on all columns because it speeds queries"
        )
        name = result["name"]

        # Manually set use_count high with zero causal hits
        db = get_db()
        with write_lock():
            db.execute(
                "UPDATE insight SET effectiveness=0.50, use_count=20, causal_hits=0 WHERE name=?",
                (name,)
            )
            db.commit()

        # Raw eff is 0.50 (above 0.25 threshold)
        # But causal-adjusted: 0.50 * max(0.3, 0/20) = 0.50 * 0.3 = 0.15
        prune_result = prune(min_effectiveness=0.25, min_uses=3)
        assert name in prune_result["removed"]
        assert get(name) is None


class TestOrphanCleanup:
    """Tests for orphan insight cleanup in prune."""

    def test_prune_cleans_orphan_insights(self, test_db, mock_embeddings):
        """NULL-embedding, never-used insights older than 7 days are cleaned."""
        from lib.memory.core import prune, get_db, write_lock, _utcnow
        from datetime import timedelta

        db = get_db()

        # Insert orphan insight (NULL embedding, use_count=0, old)
        old_date = (_utcnow() - timedelta(days=10)).isoformat()
        with write_lock():
            db.execute(
                "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) "
                "VALUES (?,?,?,?,?,?,?)",
                ("orphan-test", "Orphan insight content that nobody uses", None, 0.5, 0, old_date, "[]")
            )
            db.commit()

        # Verify it exists
        row = db.execute("SELECT * FROM insight WHERE name='orphan-test'").fetchone()
        assert row is not None

        result = prune()
        assert "orphan-test" in result["removed"]
        assert result["orphans_cleaned"] >= 1

        # Should be gone
        row = db.execute("SELECT * FROM insight WHERE name='orphan-test'").fetchone()
        assert row is None

    def test_prune_preserves_recent_orphans(self, test_db, mock_embeddings):
        """NULL-embedding insights less than 7 days old are kept (may still get embedded)."""
        from lib.memory.core import prune, get_db, write_lock, _utcnow
        from datetime import timedelta

        db = get_db()

        # Insert recent orphan (2 days old)
        recent_date = (_utcnow() - timedelta(days=2)).isoformat()
        with write_lock():
            db.execute(
                "INSERT INTO insight (name, content, embedding, effectiveness, use_count, created_at, tags) "
                "VALUES (?,?,?,?,?,?,?)",
                ("recent-orphan", "Recent orphan insight content here", None, 0.5, 0, recent_date, "[]")
            )
            db.commit()

        result = prune()
        assert "recent-orphan" not in result["removed"]


class TestStoreInitialEffectiveness:
    """Tests for custom initial effectiveness on store."""

    def test_store_initial_effectiveness(self, test_db, mock_embeddings):
        """Custom initial_effectiveness is respected."""
        from lib.memory.core import store, get

        result = store(
            content="When attempting something risky, this derived insight was auto-generated",
            tags=["derived"],
            initial_effectiveness=0.35
        )
        assert result["status"] == "added"

        insight = get(result["name"])
        assert insight["effectiveness"] == 0.35

    def test_store_default_effectiveness(self, test_db, mock_embeddings):
        """Default initial_effectiveness is 0.5."""
        from lib.memory.core import store, get

        result = store(
            content="When doing standard things, default effectiveness should be neutral"
        )

        insight = get(result["name"])
        assert insight["effectiveness"] == 0.5


class TestCount:
    """Tests for count() primitive."""

    def test_count_returns_total(self, test_db, mock_embeddings):
        """count() returns total number of insights."""
        from lib.memory.core import store, count

        assert count() == 0

        store(content="When debugging Python imports, check sys.path first because module resolution depends on it")
        assert count() == 1

        store(content="When database connection times out, add retry with exponential backoff because transient failures are common")
        assert count() == 2

    def test_count_empty_db(self, test_db):
        """count() returns 0 on empty database."""
        from lib.memory.core import count

        assert count() == 0


class TestFeedbackMixedNames:
    """Tests for feedback with mix of existing and non-existing names."""

    def test_feedback_mixed_existing_and_nonexistent(self, test_db, mock_embeddings):
        """Feedback with mix of real and fake names updates only existing ones."""
        from lib.memory.core import store, feedback

        r = store(content="When testing payment API, mock at service boundary because it improves isolation")

        result = feedback([r["name"], "nonexistent-name", "also-fake"], "delivered")

        assert result["updated"] == 1  # only the real insight
        assert result["causal"] == 1


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

    def test_health_by_tag_populated(self, test_db, mock_embeddings):
        """by_tag counts insights per tag when tagged insights exist."""
        from lib.memory.core import store, health

        store(content="When debugging Python imports, check sys.path first because module resolution depends on it",
              tags=["python", "debugging"])
        store(content="When database connections leak during exceptions, use context manager to ensure cleanup",
              tags=["python", "database"])

        h = health()
        assert h["by_tag"]["python"] == 2
        assert h["by_tag"]["debugging"] == 1
        assert h["by_tag"]["database"] == 1

    def test_health_reports_no_insights(self, test_db):
        """Health reports when no insights exist."""
        from lib.memory.core import health

        h = health()

        assert h["status"] == "NEEDS_ATTENTION"
        assert "No insights" in h["issues"][0]


class TestFeedbackRanking:
    """Tests for feedback affecting recall ranking."""

    def test_context_feedback_ranking(self, test_db, mock_embeddings):
        """Higher effectiveness insights rank higher on next recall."""
        from lib.memory.core import store, recall, feedback

        # Store two similar insights
        r1 = store(
            content="When database connections exhaust under load, increase pool size and add connection timeout"
        )
        r2 = store(
            content="When database connections leak during exceptions, use context manager and ensure cleanup in finally"
        )

        # Give r1 positive feedback
        feedback([r1["name"]], "delivered")
        feedback([r1["name"]], "delivered")

        # Give r2 negative feedback
        feedback([r2["name"]], "blocked")

        # Recall should rank r1 higher
        results = recall("database connection issues", limit=5, min_relevance=0.0)
        names = [r["name"] for r in results]

        assert r1["name"] in names, f"Expected {r1['name']} in recall results"
        assert r2["name"] in names, f"Expected {r2['name']} in recall results"
        # r1 should appear before r2 due to higher effectiveness
        assert names.index(r1["name"]) < names.index(r2["name"])
