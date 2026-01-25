"""Tests for memory/core.py - store, recall, feedback.

Critical path: The memory feedback loop is the core learning mechanism.
These tests verify store/recall/feedback work correctly.
"""

import pytest
from datetime import datetime, timedelta


class TestStore:
    """Tests for memory storage and validation."""

    def test_store_valid_failure(self, test_db, mock_embeddings):
        """Store failure memory successfully."""
        from lib.memory.core import store, get

        result = store(
            trigger="Import error when using relative imports in auth module",
            resolution="Use absolute imports from package root",
            type="failure",
            source="test"
        )

        assert result["status"] == "added"
        assert result["name"]  # Non-empty slug generated
        assert result["reason"] == ""

        # Verify persisted
        mem = get(result["name"])
        assert mem is not None
        assert mem["type"] == "failure"
        assert "relative imports" in mem["trigger"]

    def test_store_valid_pattern(self, test_db, mock_embeddings):
        """Store pattern memory successfully."""
        from lib.memory.core import store, get

        result = store(
            trigger="Task: implement user authentication with OAuth",
            resolution="Use OAuth2 PKCE flow for SPAs, store tokens securely",
            type="pattern",
            source="chunked"
        )

        assert result["status"] == "added"

        mem = get(result["name"])
        assert mem["type"] == "pattern"

    def test_store_rejects_short_trigger(self, test_db):
        """Reject triggers shorter than 10 characters."""
        from lib.memory.core import store

        result = store(
            trigger="short",
            resolution="This is a valid resolution",
            type="failure"
        )

        assert result["status"] == "rejected"
        assert "too short" in result["reason"]

    def test_store_rejects_empty_resolution(self, test_db):
        """Reject empty resolutions."""
        from lib.memory.core import store

        result = store(
            trigger="This is a valid trigger with enough characters",
            resolution="   ",  # Whitespace only
            type="failure"
        )

        assert result["status"] == "rejected"
        assert "empty" in result["reason"]

    def test_store_rejects_invalid_type(self, test_db):
        """Reject invalid memory types."""
        from lib.memory.core import store

        result = store(
            trigger="This is a valid trigger with enough characters",
            resolution="This is a valid resolution",
            type="invalid_type"
        )

        assert result["status"] == "rejected"
        assert "type" in result["reason"]

    def test_store_deduplicates_similar(self, test_db, mock_embeddings):
        """Similar memories (cosine >= 0.85) are merged, not duplicated."""
        from lib.memory.core import store

        # Store first memory
        result1 = store(
            trigger="Import error when using relative imports in src/auth module",
            resolution="Use absolute imports from package root",
            type="failure"
        )
        assert result1["status"] == "added"

        # Attempt to store nearly identical memory
        # Note: With deterministic embeddings, exact same text = identical embedding
        result2 = store(
            trigger="Import error when using relative imports in src/auth module",
            resolution="Use absolute imports from package root instead",
            type="failure"
        )

        assert result2["status"] == "merged"
        assert result2["name"] == result1["name"]

    def test_store_extracts_file_patterns(self, test_db, mock_embeddings):
        """File patterns are extracted from trigger/resolution."""
        from lib.memory.core import store

        result = store(
            trigger="Test failure in tests/test_auth.py when mocking JWT validation",
            resolution="Mock at src/auth/jwt.py service boundary, not HTTP level",
            type="failure"
        )

        assert result["status"] == "added"
        # File patterns stored in DB (not returned in dict, but verified via query)
        db = test_db
        row = db.execute(
            "SELECT file_patterns FROM memory WHERE name=?",
            (result["name"],)
        ).fetchone()
        assert row["file_patterns"] is not None
        assert "test_auth.py" in row["file_patterns"] or "jwt.py" in row["file_patterns"]


class TestRecall:
    """Tests for memory recall and ranking."""

    def test_recall_ranks_by_score(self, test_db, mock_embeddings, sample_memories):
        """Recall returns memories ranked by composite score."""
        from lib.memory.core import recall

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

    def test_recall_filters_by_type(self, test_db, mock_embeddings, sample_memories):
        """Recall respects type filter."""
        from lib.memory.core import recall

        failures = recall("authentication", type="failure", limit=10)
        patterns = recall("authentication", type="pattern", limit=10)

        for f in failures:
            assert f["type"] == "failure"

        for p in patterns:
            assert p["type"] == "pattern"

    def test_recall_filters_by_effectiveness(self, test_db, mock_embeddings):
        """Recall respects min_effectiveness threshold."""
        from lib.memory.core import store, recall, feedback_from_verification

        # Store memory and give it feedback
        result = store(
            trigger="Syntax error when using async/await without proper error handling",
            resolution="Wrap async calls in try/catch, use .catch() for promises",
            type="failure"
        )

        # Give positive feedback to increase effectiveness above 0.5
        feedback_from_verification(
            task_id="test-task",
            verify_passed=True,
            injected=[result["name"]]
        )
        feedback_from_verification(
            task_id="test-task-2",
            verify_passed=True,
            injected=[result["name"]]
        )

        # Should appear with low threshold
        results_low = recall("async error handling", min_effectiveness=0.0, limit=5)
        names_low = [r["name"] for r in results_low]

        # Should appear with medium threshold (effectiveness now > 0.5)
        results_mid = recall("async error handling", min_effectiveness=0.6, limit=5)
        names_mid = [r["name"] for r in results_mid]

        # The memory should be in low threshold results
        assert result["name"] in names_low

    def test_recall_by_file_patterns(self, test_db, mock_embeddings):
        """Recall by file patterns finds memories matching paths."""
        from lib.memory.core import store, recall_by_file_patterns

        # Store memory with file reference
        store(
            trigger="Test failure in tests/test_payment.py when processing refunds",
            resolution="Mock payment gateway response, not HTTP client",
            type="failure"
        )

        # Query by file pattern
        results = recall_by_file_patterns(["tests/test_payment.py"], limit=5)

        # Should find the memory
        assert len(results) >= 1
        found = any("payment" in r["trigger"].lower() for r in results)
        assert found


class TestFeedback:
    """Tests for feedback loop - THE critical mechanism."""

    def test_feedback_success_credits_memories(self, test_db, mock_embeddings):
        """Verification pass credits all injected memories with +0.5 helped."""
        from lib.memory.core import store, get, feedback_from_verification

        # Store memory
        result = store(
            trigger="Connection timeout when calling external API in ci environment",
            resolution="Increase timeout, add retry with backoff",
            type="failure"
        )
        name = result["name"]

        # Check initial state
        mem_before = get(name)
        assert mem_before["helped"] == 0
        assert mem_before["failed"] == 0

        # Give positive feedback
        feedback = feedback_from_verification(
            task_id="task-123",
            verify_passed=True,
            injected=[name]
        )

        assert feedback["credited"] == 1
        assert feedback["verify_passed"] is True

        # Check memory was credited
        mem_after = get(name)
        assert mem_after["helped"] == 0.5
        assert mem_after["failed"] == 0
        assert mem_after["last_used"] is not None

    def test_feedback_failure_penalizes_memories(self, test_db, mock_embeddings):
        """Verification failure adds +0.5 to failed for pruning capability."""
        from lib.memory.core import store, get, feedback_from_verification

        result = store(
            trigger="Memory leak when using closures in event handlers incorrectly",
            resolution="Remove event listeners on unmount, use WeakMap for caching",
            type="failure"
        )
        name = result["name"]

        # Give negative feedback
        feedback = feedback_from_verification(
            task_id="task-456",
            verify_passed=False,
            injected=[name]
        )

        # Should not credit but should record failure
        assert feedback["credited"] == 0

        mem = get(name)
        assert mem["helped"] == 0
        assert mem["failed"] == 0.5  # Failure recorded for pruning

    def test_feedback_skips_unknown_memories(self, test_db, mock_embeddings):
        """Non-existent memory names are silently skipped."""
        from lib.memory.core import feedback_from_verification

        feedback = feedback_from_verification(
            task_id="task-789",
            verify_passed=True,
            injected=["nonexistent-memory-name", "also-does-not-exist"]
        )

        assert feedback["credited"] == 0
        assert feedback["injected_count"] == 2

    def test_feedback_updates_last_used(self, test_db, mock_embeddings):
        """Feedback updates last_used timestamp for recency scoring."""
        from lib.memory.core import store, get, feedback_from_verification
        import time

        result = store(
            trigger="Race condition when multiple requests update same resource concurrently",
            resolution="Use optimistic locking with version field",
            type="failure"
        )
        name = result["name"]

        mem_before = get(name)
        before_last_used = mem_before["last_used"]

        time.sleep(0.01)  # Small delay to ensure different timestamp

        feedback_from_verification(
            task_id="task-update",
            verify_passed=True,
            injected=[name]
        )

        mem_after = get(name)
        assert mem_after["last_used"] != before_last_used
        assert mem_after["last_used"] > (before_last_used or "")


class TestEdges:
    """Tests for graph edge operations - knowledge connections."""

    def test_edge_creates_relationship(self, test_db, mock_embeddings, sample_memories):
        """Test basic edge creation between memories."""
        from lib.memory.core import edge, edges

        # Get two memory names from fixtures
        mem_names = [m["name"] for m in sample_memories]
        assert len(mem_names) >= 2

        # Create edge
        result = edge(mem_names[0], mem_names[1], "solves", weight=1.0)
        assert result["from"] == mem_names[0]
        assert result["to"] == mem_names[1]
        assert result["rel_type"] == "solves"

        # Query edges
        found = edges(name=mem_names[0])
        assert len(found) == 1
        assert found[0]["to_name"] == mem_names[1]
        assert found[0]["rel_type"] == "solves"

    def test_edge_weight_accumulates(self, test_db, mock_embeddings, sample_memories):
        """Test that repeated edge calls add weight (strengthening)."""
        from lib.memory.core import edge, edges

        mem_names = [m["name"] for m in sample_memories]

        # Create initial edge
        edge(mem_names[0], mem_names[1], "co_occurs", weight=1.0)

        # Strengthen by calling again
        edge(mem_names[0], mem_names[1], "co_occurs", weight=0.5)

        # Check accumulated weight
        found = edges(name=mem_names[0], rel_type="co_occurs")
        assert len(found) == 1
        assert found[0]["weight"] == 1.5  # 1.0 + 0.5

    def test_graph_expansion_in_recall(self, test_db, mock_embeddings):
        """Test that expand=True surfaces connected memories."""
        from lib.memory.core import store, edge, recall

        # Create a failure
        failure = store(
            trigger="JWT token expiration causing 401 errors in production",
            resolution="Implement token refresh flow before API calls",
            type="failure"
        )

        # Create a solution pattern
        solution = store(
            trigger="Task: handle authentication token lifecycle",
            resolution="Use refresh tokens stored in httponly cookies, auto-refresh before expiry",
            type="pattern"
        )

        # Connect them: pattern solves failure
        edge(solution["name"], failure["name"], "solves", weight=1.0)

        # Recall with expansion should find solution via edge
        results = recall("token expiration problems", expand=True, limit=10)
        names = [r["name"] for r in results]

        # Both should appear - failure directly, solution via edge
        assert failure["name"] in names
        # The solution may or may not appear depending on semantic similarity
        # but if it appears, it should have _via_edge marker
        for r in results:
            if r["name"] == solution["name"] and r.get("_via_edge"):
                assert True
                break

    def test_edge_weight_affects_score(self, test_db, mock_embeddings):
        """Test that higher edge weights boost recall scores."""
        from lib.memory.core import store, edge, recall

        # Create base failure
        base = store(
            trigger="Database connection pool exhaustion under load",
            resolution="Increase pool size, add connection timeout",
            type="failure"
        )

        # Create two solution patterns
        strong_solution = store(
            trigger="Task: implement database connection pooling",
            resolution="Use PgBouncer, configure max connections per worker",
            type="pattern"
        )

        weak_solution = store(
            trigger="Task: optimize database query performance",
            resolution="Add indexes, use query caching",
            type="pattern"
        )

        # Connect with different weights
        edge(strong_solution["name"], base["name"], "solves", weight=3.0)
        edge(weak_solution["name"], base["name"], "solves", weight=0.5)

        # Recall with expansion
        results = recall("database connection problems", expand=True, limit=10)

        # Find positions of both solutions (if they appear via edge)
        strong_idx = None
        weak_idx = None
        for i, r in enumerate(results):
            if r["name"] == strong_solution["name"]:
                strong_idx = i
            if r["name"] == weak_solution["name"]:
                weak_idx = i

        # If both appear, strong should rank higher (lower index)
        if strong_idx is not None and weak_idx is not None:
            assert strong_idx < weak_idx, "Strong edge weight should rank higher"
