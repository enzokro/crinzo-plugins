"""Tests for lib/injection.py - insight injection for agents."""

import pytest
from lib.injection import inject_context, format_prompt, build_agent_prompt, reset_session_tracking, batch_inject


class TestInjectContext:
    """Tests for inject_context function."""

    def test_inject_context_returns_structure(self, test_db, mock_embeddings, sample_insights):
        """inject_context returns expected structure."""
        result = inject_context("authentication with JWT", limit=5)

        assert "insights" in result
        assert "names" in result
        assert isinstance(result["insights"], list)
        assert isinstance(result["names"], list)

    def test_inject_context_formats_with_percentage(self, test_db, mock_embeddings, sample_insights):
        """Insights are formatted with effectiveness percentage."""
        result = inject_context("database performance", limit=5)

        for insight in result["insights"]:
            # Should have [XX%] format at start
            assert insight.startswith("[")
            assert "%]" in insight

    def test_inject_context_respects_limit(self, test_db, mock_embeddings, sample_insights):
        """limit parameter caps number of insights."""
        result = inject_context("any query", limit=2)

        assert len(result["insights"]) <= 2
        assert len(result["names"]) <= 2

    def test_inject_context_empty_db(self, test_db, mock_embeddings):
        """Handle empty database gracefully."""
        result = inject_context("anything", limit=5)

        assert result["insights"] == []
        assert result["names"] == []


class TestFormatPrompt:
    """Tests for format_prompt function."""

    def test_format_prompt_all_fields(self):
        """Format prompt with all fields."""
        result = format_prompt(
            task_id="task-001",
            task="Implement authentication",
            objective="Add JWT-based login",
            verify="Run pytest tests/test_auth.py",
            insights=["[75%] Use refresh tokens", "[60%] Store in httponly cookies"],
            injected_names=["insight-1", "insight-2"]
        )

        assert "TASK_ID: task-001" in result
        assert "TASK: Implement authentication" in result
        assert "OBJECTIVE: Add JWT-based login" in result
        assert "VERIFY: Run pytest" in result
        assert "INSIGHTS" in result
        assert "[75%] Use refresh tokens" in result
        assert "INJECTED:" in result
        assert '"insight-1"' in result

    def test_format_prompt_no_insights_emits_cold_start(self):
        """Format prompt without insights emits NO_PRIOR_MEMORY cold-start signal."""
        result = format_prompt(
            task_id="task-002",
            task="Simple task",
            objective="Do something",
            verify="Check it",
            insights=[],
            injected_names=[]
        )

        assert "TASK_ID: task-002" in result
        assert "NO_PRIOR_MEMORY" in result
        assert "Novel domain" in result
        assert "INJECTED" not in result

    def test_format_prompt_minimal(self):
        """Format prompt with minimal fields."""
        result = format_prompt(
            task_id="",
            task="Task",
            objective="Objective",
            verify="",
            insights=[],
            injected_names=[]
        )

        assert "TASK:" in result
        assert "OBJECTIVE:" in result

    def test_format_prompt_with_warning(self):
        """Format prompt includes WARNING field when provided."""
        result = format_prompt(
            task_id="010",
            task="fix-exports",
            objective="Fix barrel exports",
            verify="tsc",
            insights=[],
            injected_names=[],
            warning="CONVERGENT ISSUE: Multiple builders hit TS2308"
        )

        assert "WARNING:" in result
        assert "CONVERGENT ISSUE" in result

    def test_format_prompt_with_parent_deliveries(self):
        """Format prompt includes PARENT_DELIVERIES section."""
        result = format_prompt(
            task_id="003",
            task="build-api",
            objective="Build API",
            verify="pytest",
            insights=[],
            injected_names=[],
            parent_deliveries="[001] Models created\n[002] Schema ready"
        )

        assert "PARENT_DELIVERIES:" in result
        assert "[001] Models created" in result

    def test_format_prompt_field_order(self):
        """Fields appear in correct order: TASK_ID, WARNING, PARENT_DELIVERIES, INSIGHTS, INJECTED."""
        result = format_prompt(
            task_id="001",
            task="test",
            objective="test",
            verify="test",
            insights=["[75%] insight"],
            injected_names=["n1"],
            warning="warn",
            parent_deliveries="[000] done"
        )

        lines = result.split("\n")
        task_pos = next(i for i, l in enumerate(lines) if l.startswith("TASK_ID:"))
        warn_pos = next(i for i, l in enumerate(lines) if l.startswith("WARNING:"))
        parent_pos = next(i for i, l in enumerate(lines) if l.startswith("PARENT_DELIVERIES:"))
        insight_pos = next(i for i, l in enumerate(lines) if l.startswith("INSIGHTS"))
        injected_pos = next(i for i, l in enumerate(lines) if l.startswith("INJECTED:"))

        assert task_pos < warn_pos < parent_pos < insight_pos < injected_pos


class TestInjectContextState:
    """Tests for injection-state file writing."""

    def test_inject_context_writes_state_when_no_insights(self, test_db, mock_embeddings, meta_dir):
        """Injection-state file written even with empty names list."""
        import json
        from unittest.mock import patch

        # Empty DB → no insights will be recalled → names will be empty
        result = inject_context("nonexistent topic", limit=5, task_id="task-42")

        assert result["names"] == []

        # State file should still be written
        state_file = meta_dir / "injection-state" / "task-42.json"
        assert state_file.exists()

        data = json.loads(state_file.read_text())
        assert data["task_id"] == "task-42"
        assert data["names"] == []
        assert "ts" in data


class TestBuildAgentPrompt:
    """Tests for build_agent_prompt function."""

    def test_build_agent_prompt(self, test_db, mock_embeddings, sample_insights):
        """build_agent_prompt assembles complete prompt."""
        task_data = {
            "task_id": "task-003",
            "task": "Fix login bug",
            "objective": "Resolve authentication timeout issue",
            "verify": "Run login flow test"
        }

        result = build_agent_prompt(task_data)

        assert "TASK_ID: task-003" in result
        assert "Fix login bug" in result
        assert "authentication timeout" in result

    def test_build_agent_prompt_injects_insights(self, test_db, mock_embeddings, sample_insights):
        """build_agent_prompt includes relevant insights."""
        task_data = {
            "task_id": "task-004",
            "task": "Implement auth",
            "objective": "Add JWT authentication with refresh tokens",
            "verify": "Test auth flow"
        }

        result = build_agent_prompt(task_data)

        # Should have injected some insights about auth
        if "INSIGHTS" in result:
            assert "[" in result  # Percentage format


class TestSessionDiversity:
    """Tests for session-level injection diversity."""

    def test_diversify_excludes_already_injected(self, test_db, mock_embeddings, sample_insights):
        """Second call with diversify=True suppresses names from first call."""
        reset_session_tracking()

        result1 = inject_context("authentication with JWT", limit=5)
        names1 = set(result1["names"])

        result2 = inject_context("authentication with JWT", limit=5)
        names2 = set(result2["names"])

        # Second call should not repeat names from first (if pool is large enough)
        if names1:
            overlap = names1 & names2
            # With diversify on, no overlap expected
            assert len(overlap) == 0

    def test_diversify_false_allows_repeats(self, test_db, mock_embeddings, sample_insights):
        """diversify=False returns same results on repeated calls."""
        reset_session_tracking()

        result1 = inject_context("authentication with JWT", limit=5, diversify=False)
        result2 = inject_context("authentication with JWT", limit=5, diversify=False)

        # Same query, same results when diversity is off
        assert result1["names"] == result2["names"]

    def test_reset_session_tracking(self, test_db, mock_embeddings, sample_insights):
        """reset_session_tracking clears suppressed names."""
        reset_session_tracking()

        result1 = inject_context("authentication with JWT", limit=5)
        names1 = result1["names"]

        reset_session_tracking()

        result2 = inject_context("authentication with JWT", limit=5)
        names2 = result2["names"]

        # After reset, same names should appear again
        assert names1 == names2


class TestBatchInject:
    """Tests for batch_inject function."""

    def test_batch_inject_returns_structure(self, test_db, mock_embeddings, sample_insights):
        """batch_inject returns expected structure."""
        reset_session_tracking()

        result = batch_inject(["authentication", "database"], limit=3)

        assert "results" in result
        assert "total_unique" in result
        assert len(result["results"]) == 2
        assert isinstance(result["total_unique"], int)

    def test_batch_inject_diversifies_across_tasks(self, test_db, mock_embeddings, sample_insights):
        """Insights are diversified across batch tasks."""
        reset_session_tracking()

        result = batch_inject(["authentication", "authentication"], limit=5)

        names_1 = set(result["results"][0]["names"])
        names_2 = set(result["results"][1]["names"])

        # No overlap between tasks (diversity applied)
        if names_1:
            assert len(names_1 & names_2) == 0

    def test_batch_inject_empty_tasks(self, test_db, mock_embeddings):
        """Empty task list returns empty results."""
        reset_session_tracking()

        result = batch_inject([], limit=5)

        assert result["results"] == []
        assert result["total_unique"] == 0
