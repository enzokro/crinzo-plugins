#!/usr/bin/env python3
"""Tests for extract_learning hook module (simplified for new API)."""

import json
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))

from hooks.extract_learning import (
    _parse_transcript,
    extract_explorer_findings,
)


class TestParseTranscript:
    """Tests for _parse_transcript single-pass parser."""

    def test_extract_task_id_from_user_message(self):
        """Extract TASK_ID from user message in JSONL."""
        transcript = '{"message": {"role": "user", "content": "TASK_ID: task-123\\nTASK: Do something"}}'
        result = _parse_transcript(transcript)
        assert result.task_id == "task-123"

    def test_no_task_id(self):
        """Return None when no TASK_ID present."""
        transcript = '{"message": {"role": "user", "content": "Just a prompt without task id"}}'
        result = _parse_transcript(transcript)
        assert result.task_id is None

    def test_extracts_full_text(self):
        """Extract text content from JSONL."""
        transcript = '{"message": {"role": "user", "content": "Hello"}}\n{"message": {"role": "assistant", "content": "World"}}'
        result = _parse_transcript(transcript)
        assert "Hello" in result.full_text
        assert "World" in result.full_text

    def test_handles_list_content(self):
        """Handle content as list of text blocks."""
        transcript = '{"message": {"role": "assistant", "content": [{"type": "text", "text": "Hello"}, {"type": "text", "text": "World"}]}}'
        result = _parse_transcript(transcript)
        assert "Hello" in result.full_text
        assert "World" in result.full_text

    def test_extracts_last_assistant_message(self):
        """Return text from the final assistant message only."""
        transcript = (
            '{"message": {"role": "user", "content": "TASK_ID: t1\\nExplore src/"}}\n'
            '{"message": {"role": "assistant", "content": "Looking at files..."}}\n'
            '{"message": {"role": "assistant", "content": "{\\"status\\": \\"success\\", \\"findings\\": []}"}}'
        )
        result = _parse_transcript(transcript)
        assert result.last_assistant_text is not None
        parsed = json.loads(result.last_assistant_text)
        assert parsed["status"] == "success"

    def test_handles_list_content_blocks_last_assistant(self):
        """Handle content as list of text blocks."""
        transcript = json.dumps({
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": '{"status": "success", "findings": []}'}
                ]
            }
        })
        result = _parse_transcript(transcript)
        assert '"findings"' in result.last_assistant_text

    def test_skips_user_messages_for_last_assistant(self):
        """Only return assistant content, not user content."""
        transcript = '{"message": {"role": "user", "content": "user prompt with {braces}"}}'
        result = _parse_transcript(transcript)
        assert result.last_assistant_text is None

    def test_empty_transcript(self):
        """Return defaults for empty transcript."""
        result = _parse_transcript("")
        assert result.last_assistant_text is None
        assert result.task_id is None
        assert result.has_error is True

        result2 = _parse_transcript("  \n  ")
        assert result2.last_assistant_text is None

    def test_skips_empty_assistant_content(self):
        """Skip assistant messages with empty content."""
        transcript = (
            '{"message": {"role": "assistant", "content": "first reply"}}\n'
            '{"message": {"role": "assistant", "content": ""}}'
        )
        result = _parse_transcript(transcript)
        assert result.last_assistant_text == "first reply"

    def test_has_error_api_crash(self):
        """Detect API error in last transcript entry."""
        transcript = '{"message": {"role": "user", "content": "Do something"}}\n{"type": "error", "error": "API 500"}'
        assert _parse_transcript(transcript).has_error is True

    # test_has_error_empty removed: duplicate of test_empty_transcript above

    def test_has_error_normal(self):
        """Normal transcript does not indicate error."""
        transcript = '{"message": {"role": "assistant", "content": "DELIVERED: Done"}}'
        assert _parse_transcript(transcript).has_error is False

    def test_has_error_stop_reason(self):
        """Detect stop_reason error in message."""
        transcript = '{"message": {"role": "assistant", "content": "partial", "stop_reason": "error"}}'
        assert _parse_transcript(transcript).has_error is True


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


class TestHandoffFirst:
    """Tests verifying handoff files are written before insight processing."""

    def _make_explorer_transcript(self, tmp_path, agent_id="agent-exp-1"):
        """Create a transcript file for an explorer agent with findings."""
        transcript_lines = [
            json.dumps({"message": {"role": "user", "content": f"TASK_ID: explore-1\nTASK: Explore auth"}}),
            json.dumps({"message": {"role": "assistant", "content":
                '{"scope": "src/auth", "status": "success", "findings": [{"file": "auth.py", "what": "auth module"}]}'
            }}),
        ]
        transcript_file = tmp_path / f"{agent_id}.jsonl"
        transcript_file.write_text("\n".join(transcript_lines))
        return transcript_file

    def _make_builder_transcript(self, tmp_path, agent_id="agent-build-1"):
        """Create a transcript file for a builder agent with DELIVERED outcome."""
        transcript_lines = [
            json.dumps({"message": {"role": "user", "content": "TASK_ID: build-1\nTASK: Build feature\nINJECTED: [\"insight-a\"]"}}),
            json.dumps({"message": {"role": "assistant", "content": "DELIVERED: Feature implemented successfully"}}),
        ]
        transcript_file = tmp_path / f"{agent_id}.jsonl"
        transcript_file.write_text("\n".join(transcript_lines))
        return transcript_file

    def test_explorer_results_written_despite_insight_failure(self, tmp_path, monkeypatch):
        """Explorer results file is written even when store_insight raises."""
        from hooks import extract_learning

        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(extract_learning, "store_insight", lambda i: (_ for _ in ()).throw(RuntimeError("DB down")))

        agent_id = "agent-exp-1"
        transcript_file = self._make_explorer_transcript(tmp_path, agent_id)

        extract_learning.process_hook_input({
            "agent_type": "helix:helix-explorer",
            "agent_id": agent_id,
            "agent_transcript_path": str(transcript_file),
        })

        results_file = tmp_path / "explorer-results" / f"{agent_id}.json"
        assert results_file.exists(), "Explorer results must be written before insight processing"
        data = json.loads(results_file.read_text())
        assert data["status"] == "success"

    def test_task_status_written_despite_causal_failure(self, tmp_path, monkeypatch):
        """Task status entry is written even when filter_causal_insights raises."""
        from hooks import extract_learning

        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(extract_learning, "filter_causal_insights",
                            lambda names, ctx: (_ for _ in ()).throw(RuntimeError("Embedding model failed")))

        agent_id = "agent-build-1"
        transcript_file = self._make_builder_transcript(tmp_path, agent_id)

        extract_learning.process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": agent_id,
            "agent_transcript_path": str(transcript_file),
        })

        status_file = tmp_path / "task-status.jsonl"
        assert status_file.exists(), "Task status must be written before causal filtering"
        entries = [json.loads(l) for l in status_file.read_text().strip().splitlines()]
        assert any(e["task_id"] == "build-1" for e in entries)


class TestCrashedFeedback:
    """Tests for crashed agents generating negative feedback."""

    def _make_crashed_transcript(self, tmp_path, agent_id="agent-crash-1"):
        """Create transcript for a builder that crashed (error in last entry, no DELIVERED/BLOCKED)."""
        transcript_lines = [
            json.dumps({"message": {"role": "user", "content": "TASK_ID: crash-1\nTASK: Build feature\nINJECTED: [\"insight-a\"]"}}),
            json.dumps({"type": "error", "error": "API 500 Internal Server Error"}),
        ]
        transcript_file = tmp_path / f"{agent_id}.jsonl"
        transcript_file.write_text("\n".join(transcript_lines))
        return transcript_file

    def test_crashed_agent_applies_negative_feedback(self, tmp_path, monkeypatch):
        """Crashed agents should apply negative feedback (as blocked) to injected insights."""
        from hooks import extract_learning

        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        feedback_calls = []
        original_apply = extract_learning.apply_feedback

        def tracking_apply(names, outcome, causal_names=None):
            feedback_calls.append({"names": names, "outcome": outcome, "causal_names": causal_names})
            return True

        monkeypatch.setattr(extract_learning, "apply_feedback", tracking_apply)
        monkeypatch.setattr(extract_learning, "filter_causal_insights", lambda names, ctx: names)

        # Write sideband so injected names are found
        injected_dir = tmp_path / "injected"
        injected_dir.mkdir(exist_ok=True)
        (injected_dir / "agent-crash-1.json").write_text(json.dumps({"names": ["insight-a"], "objective": "Build feature"}))

        agent_id = "agent-crash-1"
        transcript_file = self._make_crashed_transcript(tmp_path, agent_id)

        extract_learning.process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": agent_id,
            "agent_transcript_path": str(transcript_file),
        })

        # Feedback should have been called with "blocked" outcome (crashed → blocked)
        assert len(feedback_calls) == 1
        assert feedback_calls[0]["outcome"] == "blocked"
        assert "insight-a" in feedback_calls[0]["names"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
