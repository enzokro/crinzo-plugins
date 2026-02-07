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
