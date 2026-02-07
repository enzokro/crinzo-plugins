#!/usr/bin/env python3
"""Tests for extract_learning hook module (simplified for new API)."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))

from hooks.extract_learning import (
    extract_task_id,
    get_full_transcript_text,
    extract_explorer_findings,
    _get_last_assistant_text,
    _transcript_has_error,
)


class TestExtractTaskId:
    """Tests for extract_task_id function."""

    def test_extract_from_user_message(self):
        """Extract TASK_ID from user message in JSONL."""
        transcript = '{"message": {"role": "user", "content": "TASK_ID: task-123\\nTASK: Do something"}}'
        result = extract_task_id(transcript)
        assert result == "task-123"

    def test_no_task_id(self):
        """Return None when no TASK_ID present."""
        transcript = '{"message": {"role": "user", "content": "Just a prompt without task id"}}'
        result = extract_task_id(transcript)
        assert result is None


class TestGetFullTranscriptText:
    """Tests for get_full_transcript_text function."""

    def test_extracts_content(self):
        """Extract text content from JSONL."""
        transcript = '{"message": {"role": "user", "content": "Hello"}}\n{"message": {"role": "assistant", "content": "World"}}'
        result = get_full_transcript_text(transcript)
        assert "Hello" in result
        assert "World" in result

    def test_handles_list_content(self):
        """Handle content as list of text blocks."""
        transcript = '{"message": {"role": "assistant", "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}]}}'
        result = get_full_transcript_text(transcript)
        assert "Hello" in result
        assert "World" in result


class TestGetLastAssistantText:
    """Tests for _get_last_assistant_text function."""

    def test_extracts_last_assistant_message(self):
        """Return text from the final assistant message only."""
        transcript = (
            '{"message": {"role": "user", "content": "TASK_ID: t1\\nExplore src/"}}\n'
            '{"message": {"role": "assistant", "content": "Looking at files..."}}\n'
            '{"message": {"role": "assistant", "content": "{\\"status\\": \\"success\\", \\"findings\\": []}"}}'
        )
        result = _get_last_assistant_text(transcript)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["status"] == "success"

    def test_handles_list_content_blocks(self):
        """Handle content as list of text blocks."""
        transcript = json.dumps({
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": '{"status": "success", "findings": []}'}
                ]
            }
        })
        result = _get_last_assistant_text(transcript)
        assert '"findings"' in result

    def test_skips_user_messages(self):
        """Only return assistant content, not user content."""
        transcript = '{"message": {"role": "user", "content": "user prompt with {braces}"}}'
        result = _get_last_assistant_text(transcript)
        assert result is None

    def test_empty_transcript(self):
        """Return None for empty transcript."""
        assert _get_last_assistant_text("") is None
        assert _get_last_assistant_text("  \n  ") is None

    def test_skips_empty_assistant_content(self):
        """Skip assistant messages with empty content."""
        transcript = (
            '{"message": {"role": "assistant", "content": "first reply"}}\n'
            '{"message": {"role": "assistant", "content": ""}}'
        )
        result = _get_last_assistant_text(transcript)
        assert result == "first reply"


class TestExtractExplorerFindings:
    """Tests for extract_explorer_findings function."""

    def test_extract_json_findings(self):
        """Extract JSON findings block."""
        text = '{"scope": "src", "status": "success", "findings": [{"file": "src/auth.py", "what": "auth module"}]}'
        result = extract_explorer_findings(text)
        assert result is not None
        assert result["status"] == "success"
        assert len(result["findings"]) == 1

    def test_no_findings(self):
        """Return None when no findings JSON."""
        text = "Just some text without JSON"
        result = extract_explorer_findings(text)
        assert result is None

    def test_empty_input(self):
        """Return None for empty or None input."""
        assert extract_explorer_findings("") is None
        assert extract_explorer_findings(None) is None

    def test_findings_with_leading_json_noise(self):
        """Extract findings even when earlier JSON objects exist in text."""
        text = (
            'Some preamble with {"type": "tool_call", "name": "Grep"} noise '
            'and more {"irrelevant": true} stuff. '
            'Here is the result: {"scope": "lib", "status": "success", '
            '"findings": [{"file": "lib/core.py", "what": "core module"}]}'
        )
        result = extract_explorer_findings(text)
        assert result is not None
        assert result["status"] == "success"
        assert result["findings"][0]["file"] == "lib/core.py"

    def test_backward_scan_skips_non_findings_json(self):
        """Backward scan skips JSON objects without findings/status keys."""
        text = (
            '{"status": "success", "findings": [{"file": "a.py", "what": "target"}]} '
            'then some trailing {"unrelated": "data"}'
        )
        result = extract_explorer_findings(text)
        assert result is not None
        assert result["status"] == "success"

    def test_realistic_flattened_transcript(self):
        """Extract from flattened transcript with system reminders and user prompts."""
        text = (
            '<system-reminder>{"config": {"model": "opus"}}</system-reminder>\n'
            'TASK_ID: explore-1\nTASK: Explore authentication\n'
            'INJECTED: ["insight-auth-1"]\n'
            'Looking at the codebase structure...\n'
            'I found the relevant files.\n'
            '{"scope": "src/auth", "status": "success", '
            '"findings": [{"file": "src/auth/login.py", "what": "login handler"}]}'
        )
        result = extract_explorer_findings(text)
        assert result is not None
        assert result["scope"] == "src/auth"
        assert len(result["findings"]) == 1


class TestTranscriptHasError:
    """Tests for _transcript_has_error function."""

    def test_transcript_has_error_api_crash(self):
        """Detect API error in last transcript entry."""
        transcript = '{"message": {"role": "user", "content": "Do something"}}\n{"type": "error", "error": "API 500"}'
        assert _transcript_has_error(transcript) is True

    def test_transcript_has_error_empty(self):
        """Empty transcript indicates crash."""
        assert _transcript_has_error("") is True
        assert _transcript_has_error("   \n  ") is True

    def test_transcript_has_error_normal(self):
        """Normal transcript does not indicate error."""
        transcript = '{"message": {"role": "assistant", "content": "DELIVERED: Done"}}'
        assert _transcript_has_error(transcript) is False

    def test_transcript_has_error_stop_reason(self):
        """Detect stop_reason error in message."""
        transcript = '{"message": {"role": "assistant", "content": "partial", "stop_reason": "error"}}'
        assert _transcript_has_error(transcript) is True


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
