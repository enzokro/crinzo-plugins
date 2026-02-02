"""Tests for wait.py - Wait-polling utilities.

Tests completion detection, waiting, and content extraction.
"""

import json
import pytest
from pathlib import Path


class TestMarkers:
    """Tests for MARKERS constant."""

    def test_markers_has_expected_agent_types(self):
        """MARKERS dict has all agent types."""
        from lib.wait import MARKERS

        assert "builder" in MARKERS
        assert "explorer" in MARKERS
        assert "planner" in MARKERS

    def test_builder_markers(self):
        """Builder has DELIVERED and BLOCKED markers."""
        from lib.wait import MARKERS

        assert "DELIVERED:" in MARKERS["builder"]
        assert "BLOCKED:" in MARKERS["builder"]

    def test_explorer_markers(self):
        """Explorer has status marker."""
        from lib.wait import MARKERS

        assert '"status":' in MARKERS["explorer"]

    def test_planner_markers(self):
        """Planner has PLAN_COMPLETE and ERROR markers."""
        from lib.wait import MARKERS

        assert "PLAN_COMPLETE:" in MARKERS["planner"]
        assert "ERROR:" in MARKERS["planner"]


class TestDetectCompletion:
    """Tests for detect_completion function.

    Note: detect_completion expects JSONL format with message.role = "assistant"
    """

    def test_detect_builder_delivered(self, tmp_path):
        """Detects DELIVERED marker in builder output."""
        from lib.wait import detect_completion

        output_file = tmp_path / "builder.jsonl"
        # JSONL format with assistant message
        output_file.write_text('{"message": {"role": "assistant", "content": "DELIVERED: Added auth module"}}\n')

        result = detect_completion(str(output_file), "builder")

        assert result is not None
        marker, content = result
        assert marker == "DELIVERED:"
        assert "Added auth module" in content

    def test_detect_builder_blocked(self, tmp_path):
        """Detects BLOCKED marker in builder output."""
        from lib.wait import detect_completion

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "BLOCKED: Tests failed"}}\n')

        result = detect_completion(str(output_file), "builder")

        assert result is not None
        marker, content = result
        assert marker == "BLOCKED:"
        assert "Tests failed" in content

    def test_detect_explorer_success(self, tmp_path):
        """Detects status marker in explorer output."""
        from lib.wait import detect_completion

        output_file = tmp_path / "explorer.jsonl"
        # Explorer outputs JSON with status field in assistant message
        output_file.write_text('{"message": {"role": "assistant", "content": "{\\"scope\\": \\"src/\\", \\"status\\": \\"success\\", \\"findings\\": []}"}}\n')

        result = detect_completion(str(output_file), "explorer")

        assert result is not None
        marker, content = result
        assert marker == '"status":'

    def test_detect_planner_complete(self, tmp_path):
        """Detects PLAN_COMPLETE marker in planner output."""
        from lib.wait import detect_completion

        output_file = tmp_path / "planner.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "PLAN_COMPLETE: 3 tasks created"}}\n')

        result = detect_completion(str(output_file), "planner")

        assert result is not None
        marker, content = result
        assert marker == "PLAN_COMPLETE:"
        assert "3 tasks created" in content

    def test_detect_no_completion(self, tmp_path):
        """Returns None when no completion marker found."""
        from lib.wait import detect_completion

        output_file = tmp_path / "incomplete.jsonl"
        output_file.write_text('{"type": "tool_call"}\n{"type": "working"}\n')

        result = detect_completion(str(output_file), "builder")

        assert result is None

    def test_detect_nonexistent_file(self, tmp_path):
        """Returns None for nonexistent file."""
        from lib.wait import detect_completion

        result = detect_completion(str(tmp_path / "nonexistent.jsonl"), "builder")

        assert result is None

    def test_detect_invalid_agent_type(self, tmp_path):
        """Raises error for unknown agent type."""
        from lib.wait import detect_completion

        output_file = tmp_path / "test.jsonl"
        output_file.write_text("test content\n")

        with pytest.raises(ValueError) as exc_info:
            detect_completion(str(output_file), "unknown_agent")

        assert "Unknown agent type" in str(exc_info.value)


class TestWaitForCompletion:
    """Tests for wait_for_completion function."""

    def test_wait_immediate_completion(self, tmp_path):
        """Returns immediately when already completed."""
        from lib.wait import wait_for_completion

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "DELIVERED: Done"}}\n')

        result = wait_for_completion(str(output_file), "builder", timeout_sec=1.0, poll_interval=0.1)

        assert result.completed is True
        assert result.marker == "DELIVERED:"
        assert result.timed_out is False

    def test_wait_timeout(self, tmp_path):
        """Returns timeout when not completed within time."""
        from lib.wait import wait_for_completion

        output_file = tmp_path / "incomplete.jsonl"
        output_file.write_text("working...\n")

        result = wait_for_completion(str(output_file), "builder", timeout_sec=0.5, poll_interval=0.1)

        assert result.completed is False
        assert result.timed_out is True

    def test_wait_invalid_agent_type(self, tmp_path):
        """Returns error for unknown agent type."""
        from lib.wait import wait_for_completion

        output_file = tmp_path / "test.jsonl"
        output_file.write_text("test\n")

        result = wait_for_completion(str(output_file), "invalid", timeout_sec=0.1)

        assert result.completed is False
        assert result.error is not None
        assert "Unknown agent type" in result.error


class TestGetCompletionContent:
    """Tests for get_completion_content function."""

    def test_get_builder_delivered_content(self, tmp_path):
        """Extracts delivered content from builder output."""
        from lib.wait import get_completion_content

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "DELIVERED: Added user authentication"}}\n')

        content = get_completion_content(str(output_file), "builder")

        assert content is not None
        assert content["outcome"] == "delivered"
        assert "user authentication" in content["summary"]

    def test_get_builder_blocked_content(self, tmp_path):
        """Extracts blocked content from builder output."""
        from lib.wait import get_completion_content

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "BLOCKED: Database connection failed"}}\n')

        content = get_completion_content(str(output_file), "builder")

        assert content is not None
        assert content["outcome"] == "blocked"
        assert "Database connection" in content["reason"]

    def test_get_planner_complete_content(self, tmp_path):
        """Extracts plan complete content from planner output."""
        from lib.wait import get_completion_content

        output_file = tmp_path / "planner.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "PLAN_COMPLETE: 5 tasks created"}}\n')

        content = get_completion_content(str(output_file), "planner")

        assert content is not None
        assert content["status"] == "complete"
        assert "5 tasks" in content["detail"]

    def test_get_planner_error_content(self, tmp_path):
        """Extracts error content from planner output."""
        from lib.wait import get_completion_content

        output_file = tmp_path / "planner.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "ERROR: TaskCreate not available"}}\n')

        content = get_completion_content(str(output_file), "planner")

        assert content is not None
        assert content["status"] == "error"
        assert "TaskCreate" in content["detail"]

    def test_get_incomplete_returns_none(self, tmp_path):
        """Returns None for incomplete output."""
        from lib.wait import get_completion_content

        output_file = tmp_path / "incomplete.jsonl"
        output_file.write_text("working...\n")

        content = get_completion_content(str(output_file), "builder")

        assert content is None


class TestGetLastJsonBlock:
    """Tests for get_last_json_block function."""

    def test_get_last_json_single_block(self, tmp_path):
        """Extracts single JSON block."""
        from lib.wait import get_last_json_block

        output_file = tmp_path / "explorer.jsonl"
        output_file.write_text('{"scope": "src/", "status": "success", "findings": []}')

        result = get_last_json_block(str(output_file))

        assert result is not None
        assert result["scope"] == "src/"
        assert result["status"] == "success"

    def test_get_last_json_multiple_blocks(self, tmp_path):
        """Returns last JSON block when multiple exist."""
        from lib.wait import get_last_json_block

        output_file = tmp_path / "output.jsonl"
        output_file.write_text('{"first": true}\n{"second": true}\n{"last": true}')

        result = get_last_json_block(str(output_file))

        assert result is not None
        assert result.get("last") is True

    def test_get_last_json_with_text(self, tmp_path):
        """Extracts JSON when mixed with text."""
        from lib.wait import get_last_json_block

        output_file = tmp_path / "mixed.jsonl"
        output_file.write_text('Some text\n{"data": "value"}\nMore text')

        result = get_last_json_block(str(output_file))

        assert result is not None
        assert result["data"] == "value"

    def test_get_last_json_nonexistent_file(self, tmp_path):
        """Returns None for nonexistent file."""
        from lib.wait import get_last_json_block

        result = get_last_json_block(str(tmp_path / "nonexistent.jsonl"))

        assert result is None

    def test_get_last_json_no_json(self, tmp_path):
        """Returns None when no JSON in file."""
        from lib.wait import get_last_json_block

        output_file = tmp_path / "text.txt"
        output_file.write_text("Just plain text\nNo JSON here")

        result = get_last_json_block(str(output_file))

        assert result is None


class TestCLI:
    """Tests for CLI interface."""

    def test_cli_check_completed(self, tmp_path):
        """CLI check returns completed status."""
        import subprocess
        import sys

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "DELIVERED: Done"}}\n')

        result = subprocess.run(
            [sys.executable, "-m", "lib.wait", "check",
             "--output-file", str(output_file),
             "--agent-type", "builder"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["completed"] is True
        assert data["marker"] == "DELIVERED:"

    def test_cli_check_not_completed(self, tmp_path):
        """CLI check returns not completed status."""
        import subprocess
        import sys

        output_file = tmp_path / "incomplete.jsonl"
        output_file.write_text("working...\n")

        result = subprocess.run(
            [sys.executable, "-m", "lib.wait", "check",
             "--output-file", str(output_file),
             "--agent-type", "builder"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["completed"] is False

    def test_cli_extract(self, tmp_path):
        """CLI extract returns structured content."""
        import subprocess
        import sys

        output_file = tmp_path / "builder.jsonl"
        output_file.write_text('{"message": {"role": "assistant", "content": "DELIVERED: Added feature"}}\n')

        result = subprocess.run(
            [sys.executable, "-m", "lib.wait", "extract",
             "--output-file", str(output_file),
             "--agent-type", "builder"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["extracted"] is True
        assert data["content"]["outcome"] == "delivered"

    def test_cli_last_json(self, tmp_path):
        """CLI last-json extracts JSON block."""
        import subprocess
        import sys

        output_file = tmp_path / "explorer.jsonl"
        output_file.write_text('{"status": "success", "findings": []}')

        result = subprocess.run(
            [sys.executable, "-m", "lib.wait", "last-json",
             "--output-file", str(output_file)],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent
        )

        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["found"] is True
        assert data["content"]["status"] == "success"
