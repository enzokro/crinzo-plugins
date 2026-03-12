"""Tests for cross-session pattern synthesis."""
import json
import pytest
from datetime import datetime, timezone


def _insert_session_log(db, agent_type, outcome, summary, created_at=None):
    """Insert a session_log entry."""
    if created_at is None:
        created_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    db.execute(
        "INSERT INTO session_log (agent_id, agent_type, task_id, outcome, summary, transcript_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (f"agent-{id(summary)}", agent_type, "task-1", outcome, summary, f"hash-{id(summary)}", created_at)
    )
    db.commit()


class TestSynthesisEmpty:
    def test_no_sessions_returns_empty(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        assert synthesize_session() == []

    def test_below_threshold_returns_empty(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        _insert_session_log(test_db, "builder", "blocked", "Auth token expired during test")
        _insert_session_log(test_db, "builder", "blocked", "Auth token validation failed")
        # Only 2, threshold is 3
        assert synthesize_session() == []


class TestSynthesisPatternDetection:
    def test_detects_repeated_blocker(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        for i in range(4):
            _insert_session_log(test_db, "builder", "blocked",
                                f"Authentication token refresh failed during test run {i}")
        result = synthesize_session()
        assert len(result) >= 1
        assert result[0]["type"] in ("new", "reinforcement")
        assert "builder" in result[0]["content"]
        assert "strategic" in result[0]["tags"]

    def test_ignores_delivered_sessions(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        for i in range(5):
            _insert_session_log(test_db, "builder", "delivered",
                                f"Successfully built auth module iteration {i}")
        assert synthesize_session() == []

    def test_crashed_counts_as_failure(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        for i in range(4):
            _insert_session_log(test_db, "builder", "crashed",
                                f"Payment processing crashed with timeout error {i}")
        result = synthesize_session()
        assert len(result) >= 1

    def test_pattern_content_prescriptive(self, test_db, mock_embeddings):
        from lib.memory.synthesis import synthesize_session
        for i in range(4):
            _insert_session_log(test_db, "planner", "blocked",
                                f"Database migration planning failed on schema {i}")
        result = synthesize_session()
        assert len(result) >= 1
        # Content should be prescriptive
        assert "planner" in result[0]["content"]
        assert "block" in result[0]["content"].lower()


class TestSynthesisCommonTerms:
    def test_extract_common_terms(self):
        from lib.memory.synthesis import _extract_common_terms
        summaries = [
            "Authentication token expired during test",
            "Authentication failed on token refresh",
            "Token authentication error in integration test",
        ]
        terms = _extract_common_terms(summaries, top_n=3)
        assert "authentication" in terms or "token" in terms


class TestClusterSummaries:
    def test_groups_similar_summaries(self, test_db, mock_embeddings):
        from lib.memory.synthesis import _cluster_summaries
        # With mock embeddings (hash-based), similar text produces similar hashes
        summaries = [
            "Authentication token expired during test run",
            "Authentication token validation failed in test",
            "Auth token refresh error during testing phase",
            "Database connection timeout on startup check",
        ]
        clusters = _cluster_summaries(summaries)
        assert len(clusters) >= 1  # At least one cluster formed
        # All clusters have required fields
        for c in clusters:
            assert "representative" in c
            assert "members" in c
            assert "tightness" in c
            assert "confidence" in c

    def test_single_summary(self, test_db, mock_embeddings):
        from lib.memory.synthesis import _cluster_summaries
        clusters = _cluster_summaries(["Single summary here"])
        assert len(clusters) == 1
        assert clusters[0]["representative"] == "Single summary here"

    def test_empty_summaries(self, test_db, mock_embeddings):
        from lib.memory.synthesis import _cluster_summaries
        assert _cluster_summaries([]) == []
        assert _cluster_summaries(["", None, "  "]) == []

    def test_cluster_has_confidence(self, test_db, mock_embeddings):
        from lib.memory.synthesis import _cluster_summaries
        summaries = [
            "Build failed due to missing dependency A",
            "Build failed due to missing dependency B",
            "Build failed due to missing dependency C",
            "Build failed due to missing dependency D",
        ]
        clusters = _cluster_summaries(summaries)
        # With mock embeddings all merge into one cluster
        assert len(clusters) >= 1
        for c in clusters:
            assert c["confidence"] > 0
            assert 0 <= c["tightness"] <= 1.0

    def test_representative_is_from_members(self, test_db, mock_embeddings):
        from lib.memory.synthesis import _cluster_summaries
        summaries = [
            "Config file parsing error in yaml module",
            "YAML config validation failure on startup",
            "Configuration parse error for settings.yml",
        ]
        clusters = _cluster_summaries(summaries)
        for c in clusters:
            assert c["representative"] in c["members"]
