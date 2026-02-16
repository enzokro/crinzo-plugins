"""Tests for causal filtering in extract_learning.py.

Verifies:
- filter_causal_insights() correctly filters by semantic similarity
- process_hook_input() wires causal filtering into feedback
- write_task_status() includes insight_content
- log_extraction_result() includes causal stats
"""

import json

import pytest


pytestmark = pytest.mark.usefixtures("isolated_env")


class TestFilterCausalInsights:
    """Tests for filter_causal_insights function."""

    def test_empty_names_returns_empty(self):
        """Empty injected names returns empty list."""
        from lib.hooks.extract_learning import filter_causal_insights
        assert filter_causal_insights([], "some context") == []

    def test_empty_context_returns_all(self):
        """Empty task context returns all names (graceful fallback)."""
        from lib.hooks.extract_learning import filter_causal_insights
        names = ["insight-a", "insight-b"]
        assert filter_causal_insights(names, "") == names

    def test_filters_irrelevant_insights(self):
        """Insights semantically unrelated to task context are filtered out."""
        from lib.memory.core import store
        from lib.hooks.extract_learning import filter_causal_insights

        # Store one relevant and one irrelevant insight
        r1 = store("When testing TypeScript barrel exports, check index.ts re-exports all modules", tags=["ts"])
        r2 = store("When cooking pasta, always use salted boiling water for best flavor results", tags=["cooking"])

        context = "Implement TypeScript barrel export system with proper index.ts re-exports"
        result = filter_causal_insights([r1["name"], r2["name"]], context)

        # TS insight should pass, cooking should not
        assert r1["name"] in result
        assert r2["name"] not in result, "Cooking insight should be filtered as irrelevant to TypeScript context"

    def test_nonexistent_insight_skipped(self):
        """Non-existent insight names are skipped without error."""
        from lib.hooks.extract_learning import filter_causal_insights
        result = filter_causal_insights(["nonexistent-insight"], "some TypeScript context")
        assert result == []


class TestWriteTaskStatus:
    """Tests for enriched write_task_status."""

    def test_includes_insight_content(self, isolated_env):
        """write_task_status includes insight field when provided."""
        from lib.hooks.extract_learning import write_task_status

        write_task_status(
            "task-001", "agent-abc", "delivered", "Summary here",
            insight_content="When testing X, do Y because Z"
        )

        status_file = isolated_env / ".helix" / "task-status.jsonl"
        assert status_file.exists()

        entry = json.loads(status_file.read_text().strip())
        assert entry["insight"] == "When testing X, do Y because Z"

    def test_no_insight_field_when_none(self, isolated_env):
        """write_task_status omits insight field when None."""
        from lib.hooks.extract_learning import write_task_status

        write_task_status("task-002", "agent-xyz", "delivered", "Summary")

        status_file = isolated_env / ".helix" / "task-status.jsonl"
        entry = json.loads(status_file.read_text().strip())
        assert "insight" not in entry


class TestLogExtractionResult:
    """Tests for enriched log_extraction_result."""

    def test_includes_causal_stats(self, isolated_env):
        """Log includes causal=N/M when causal_count provided."""
        from lib.hooks.extract_learning import log_extraction_result

        result = {"outcome": "delivered", "insight": {"content": "test"}, "injected": ["a", "b", "c"]}
        log_extraction_result("agent-1", "helix:helix-builder", result,
                              feedback_applied=True, causal_count=2, total_injected=3)

        log_file = isolated_env / ".helix" / "extraction.log"
        log_content = log_file.read_text()
        assert "causal=2/3" in log_content

    def test_no_causal_stats_when_none(self, isolated_env):
        """Log omits causal stats when causal_count is None."""
        from lib.hooks.extract_learning import log_extraction_result

        result = {"outcome": "delivered", "insight": None, "injected": []}
        log_extraction_result("agent-2", "helix:helix-builder", result)

        log_file = isolated_env / ".helix" / "extraction.log"
        log_content = log_file.read_text()
        assert "causal=" not in log_content


class TestApplyFeedback:
    """Tests for updated apply_feedback with causal_names."""

    def test_returns_false_for_empty_names(self):
        """apply_feedback returns False for empty names."""
        from lib.hooks.extract_learning import apply_feedback

        assert apply_feedback([], "delivered", causal_names=[]) is False

    def test_returns_false_for_invalid_outcome(self):
        """apply_feedback returns False for invalid outcome."""
        from lib.hooks.extract_learning import apply_feedback

        assert apply_feedback(["some-name"], "invalid", causal_names=None) is False

    # test_causal_feedback_integration removed: duplicate of
    # test_causal_feedback.py::TestDualPathFeedback::test_causal_insight_gets_ema_update
