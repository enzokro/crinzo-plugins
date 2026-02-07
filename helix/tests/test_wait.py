"""Tests for wait.py - Wait-polling utilities.

Tests the active wait functions: wait_for_explorer_results, wait_for_builder_results.
"""

import json
import pytest
from pathlib import Path


class TestWaitForExplorerResults:
    """Tests for wait_for_explorer_results function."""

    def test_wait_explorer_results_found(self, tmp_path):
        """Returns merged findings when all explorer results arrive."""
        from lib.wait import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Write two explorer result files
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/a.py", "what": "module A"}]
        }))
        (results_dir / "agent-2.json").write_text(json.dumps({
            "findings": [{"file": "src/b.py", "what": "module B"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["count"] == 2
        assert len(result["findings"]) == 2

    def test_wait_explorer_results_timeout(self, tmp_path):
        """Returns partial results on timeout."""
        from lib.wait import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Only one of two expected
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/a.py", "what": "module A"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=0.3,
            poll_interval=0.1
        )

        assert result["completed"] is False
        assert result["timed_out"] is True
        assert result["count"] == 1

    def test_wait_explorer_deduplicates(self, tmp_path):
        """Deduplicates findings by file path."""
        from lib.wait import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Two explorers find the same file
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 1"}]
        }))
        (results_dir / "agent-2.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 2"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert len(result["findings"]) == 1  # Deduped

    def test_wait_explorer_handles_errors(self, tmp_path):
        """Reports errors from failed explorers."""
        from lib.wait import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        (results_dir / "agent-1.json").write_text(json.dumps({
            "status": "error", "error": "Scope not found"
        }))

        result = wait_for_explorer_results(
            expected_count=1,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["errors"] is not None
        assert "Scope not found" in result["errors"][0]


class TestWaitForBuilderResults:
    """Tests for wait_for_builder_results function."""

    def test_wait_builder_unknown_not_delivered(self, tmp_path):
        """Tasks with unknown outcome cause all_delivered=False."""
        from lib.wait import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "unknown", "summary": ""}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is False
        assert len(result["unknown"]) == 1
        assert result["unknown"][0]["task_id"] == "task-2"

    def test_wait_builder_all_delivered(self, tmp_path):
        """All delivered tasks => all_delivered=True."""
        from lib.wait import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is True
        assert len(result["unknown"]) == 0

    def test_wait_builder_timeout(self, tmp_path):
        """Returns partial results on timeout."""
        from lib.wait import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=0.3,
            poll_interval=0.1
        )

        assert result["completed"] is False
        assert result["timed_out"] is True
        assert "task-2" in result["missing"]

    def test_wait_builder_blocked(self, tmp_path):
        """Blocked tasks are categorized correctly."""
        from lib.wait import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "blocked", "summary": "tests failed"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is False
        assert len(result["blocked"]) == 1
        assert len(result["delivered"]) == 1

    def test_wait_builder_insights_emitted(self, tmp_path):
        """Counts insights_emitted from task status entries."""
        from lib.wait import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done", "insight": "When X, do Y"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["insights_emitted"] == 1
