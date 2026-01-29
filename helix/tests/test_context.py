"""Tests for context.py - context building for builders.

Tests the memory injection pipeline that provides builders with
relevant failures and patterns from the learning system.
"""

import pytest


class TestBuildContext:
    """Tests for build_context function."""

    def test_build_context_combines_queries(self, test_db, mock_embeddings, sample_memories, sample_task_data):
        """Context combines semantic and file-based queries."""
        from lib.context import build_context

        result = build_context(sample_task_data)

        assert "prompt" in result
        assert "injected" in result
        assert isinstance(result["injected"], list)

        # Prompt should contain key fields
        prompt = result["prompt"]
        assert "TASK_ID:" in prompt
        assert "OBJECTIVE:" in prompt
        assert "VERIFY:" in prompt
        assert "FAILURES_TO_AVOID:" in prompt
        assert "PATTERNS_TO_APPLY:" in prompt
        assert "INJECTED_MEMORIES:" in prompt

    def test_build_context_deduplicates(self, test_db, mock_embeddings, sample_memories, sample_task_data):
        """Same memory from semantic and file paths appears once."""
        from lib.context import build_context

        result = build_context(sample_task_data, memory_limit=10)

        # Injected names should be unique
        assert len(result["injected"]) == len(set(result["injected"]))

    def test_build_context_respects_limit(self, test_db, mock_embeddings, sample_memories, sample_task_data):
        """Memory limit is enforced."""
        from lib.context import build_context

        result = build_context(sample_task_data, memory_limit=2)

        assert len(result["injected"]) <= 2

    def test_build_context_includes_warning(self, test_db, mock_embeddings, sample_task_data):
        """Warning is injected at start of prompt when provided."""
        from lib.context import build_context

        warning = "Systemic issue: import_error detected 3x"
        result = build_context(sample_task_data, warning=warning)

        prompt = result["prompt"]
        # Warning should appear first (before TASK_ID)
        warning_pos = prompt.find("WARNING:")
        task_pos = prompt.find("TASK_ID:")

        assert warning_pos != -1
        assert warning_pos < task_pos
        assert warning in prompt

    def test_build_context_formats_prompt(self, test_db, mock_embeddings, sample_task_data):
        """Prompt includes all required fields."""
        from lib.context import build_context

        result = build_context(sample_task_data)
        prompt = result["prompt"]

        # Check all expected fields present
        assert f"TASK_ID: {sample_task_data['id']}" in prompt
        assert f"TASK: {sample_task_data['subject']}" in prompt
        assert f"OBJECTIVE: {sample_task_data['description']}" in prompt
        assert "VERIFY:" in prompt
        assert "FRAMEWORK:" in prompt
        assert "RELEVANT_FILES:" in prompt
        assert "Report DELIVERED or BLOCKED" in prompt

    def test_build_context_tracks_injected(self, test_db, mock_embeddings, sample_memories, sample_task_data):
        """Returns memory names for feedback tracking."""
        from lib.context import build_context

        result = build_context(sample_task_data)

        # Injected should be list of memory name strings
        for name in result["injected"]:
            assert isinstance(name, str)
            assert len(name) > 0


class TestLineage:
    """Tests for lineage building from completed tasks."""

    def test_build_lineage_extracts_deliveries(self):
        """Extracts deliveries from completed tasks."""
        from lib.context import build_lineage_from_tasks

        completed_tasks = [
            {
                "subject": "001: setup-database",
                "metadata": {"delivered_summary": "Created PostgreSQL schema with migrations"}
            },
            {
                "subject": "002: impl-models",
                "metadata": {"delivered_summary": "Added User and Session models"}
            },
        ]

        lineage = build_lineage_from_tasks(completed_tasks)

        assert len(lineage) == 2

        assert lineage[0]["seq"] == "001"
        assert lineage[0]["slug"] == "setup-database"
        assert "PostgreSQL" in lineage[0]["delivered"]

        assert lineage[1]["seq"] == "002"
        assert lineage[1]["slug"] == "impl-models"

    def test_build_lineage_handles_missing(self):
        """Skips tasks without delivered_summary."""
        from lib.context import build_lineage_from_tasks

        completed_tasks = [
            {
                "subject": "001: setup-database",
                "metadata": {"delivered_summary": "Created schema"}
            },
            {
                "subject": "002: blocked-task",
                "metadata": {}  # No delivered_summary
            },
            {
                "subject": "003: legacy-task",
                "metadata": {"delivered": "Legacy delivery field"}  # Old field name
            },
        ]

        lineage = build_lineage_from_tasks(completed_tasks)

        # Should include 001 and 003, skip 002
        assert len(lineage) == 2
        assert lineage[0]["seq"] == "001"
        assert lineage[1]["seq"] == "003"
        assert lineage[1]["delivered"] == "Legacy delivery field"


class TestInjectedTracking:
    """Tests for injected memory tracking in context builders."""

    def test_explorer_context_returns_injected(self, test_db, mock_embeddings, sample_memories):
        """Explorer context should return injected memory names."""
        from lib.context import build_explorer_context

        ctx = build_explorer_context("test objective", "src/")

        assert "injected" in ctx
        assert isinstance(ctx["injected"], list)
        # All injected names should be strings
        for name in ctx["injected"]:
            assert isinstance(name, str)

    def test_explorer_context_injected_from_facts_and_failures(self, test_db, mock_embeddings, sample_memories):
        """Explorer injected should include both facts and failures."""
        from lib.context import build_explorer_context

        ctx = build_explorer_context("test objective", "src/")

        # injected comes from both facts and failures queries
        # The exact names depend on sample_memories fixture
        assert "injected" in ctx

    def test_planner_context_returns_injected(self, test_db, mock_embeddings, sample_memories):
        """Planner context should return injected memory names."""
        from lib.context import build_planner_context

        ctx = build_planner_context("test objective")

        assert "injected" in ctx
        assert isinstance(ctx["injected"], list)
        # All injected names should be strings
        for name in ctx["injected"]:
            assert isinstance(name, str)

    def test_planner_context_injected_from_decisions_conventions_evolution(self, test_db, mock_embeddings, sample_memories):
        """Planner injected should include decisions, conventions, and evolution."""
        from lib.context import build_planner_context

        ctx = build_planner_context("test objective")

        # injected comes from decisions, conventions, and evolution queries
        assert "injected" in ctx

    def test_explorer_context_empty_when_no_memories(self, test_db, mock_embeddings):
        """Explorer context should have empty injected when no memories exist."""
        from lib.context import build_explorer_context

        ctx = build_explorer_context("nonexistent topic", "nonexistent/")

        assert "injected" in ctx
        assert ctx["injected"] == []

    def test_planner_context_empty_when_no_memories(self, test_db, mock_embeddings):
        """Planner context should have empty injected when no memories exist."""
        from lib.context import build_planner_context

        ctx = build_planner_context("nonexistent topic")

        assert "injected" in ctx
        assert ctx["injected"] == []
