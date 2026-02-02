#!/usr/bin/env python3
"""Tests for extract_learning hook module."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))

from hooks.extract_learning import (
    extract_learned_field,
    extract_outcome,
    extract_findings_section,
    extract_learned_block,
    extract_builder_candidates,
    extract_explorer_candidates,
    extract_planner_candidates,
    process_transcript,
)


class TestExtractLearnedField:
    """Tests for extract_learned_field function.

    Expects JSONL transcript format with assistant messages.
    """

    def test_json_format(self):
        # JSONL format with assistant message containing learned field
        transcript = '{"message": {"role": "assistant", "content": "learned: {\\"type\\": \\"pattern\\", \\"trigger\\": \\"When X\\", \\"resolution\\": \\"Do Y\\"}"}}'
        result = extract_learned_field(transcript)
        assert result is not None
        assert result["type"] == "pattern"
        assert result["trigger"] == "When X"

    def test_quoted_format(self):
        # JSONL format with quoted learned field
        transcript = '{"message": {"role": "assistant", "content": "\\"learned\\": {\\"type\\": \\"failure\\", \\"trigger\\": \\"Error X\\", \\"resolution\\": \\"Fix Y\\"}"}}'
        result = extract_learned_field(transcript)
        assert result is not None
        assert result["type"] == "failure"

    def test_no_learned_field(self):
        transcript = "Just some regular text with no learning."
        result = extract_learned_field(transcript)
        assert result is None


class TestExtractOutcome:
    """Tests for extract_outcome function."""

    def test_delivered(self):
        transcript = "DELIVERED: Added the feature"
        assert extract_outcome(transcript) == "delivered"

    def test_blocked(self):
        transcript = "BLOCKED: Could not find file"
        assert extract_outcome(transcript) == "blocked"

    def test_unknown(self):
        transcript = "Some random text"
        assert extract_outcome(transcript) == "unknown"

    def test_case_insensitive(self):
        transcript = "delivered: done"
        assert extract_outcome(transcript) == "delivered"


class TestExtractFindingsSection:
    """Tests for extract_findings_section function.

    Contract mandates JSON output. Markdown fallbacks removed.
    """

    def test_json_findings(self):
        # Simulate JSONL transcript with JSON findings in assistant message
        transcript = '{"message": {"role": "assistant", "content": "{\\"scope\\": \\"src\\", \\"status\\": \\"success\\", \\"findings\\": [{\\"file\\": \\"src/auth.py\\", \\"what\\": \\"auth module\\"}]}"}}'
        findings = extract_findings_section(transcript)
        assert len(findings) == 1
        assert findings[0]["file"] == "src/auth.py"

    def test_markdown_returns_empty(self):
        # Markdown format is no longer supported - returns empty
        transcript = '''
## FINDINGS
- Found auth module at src/auth.py
'''
        findings = extract_findings_section(transcript)
        assert findings == []

    def test_no_findings(self):
        transcript = "Just some text without findings"
        findings = extract_findings_section(transcript)
        assert findings == []


class TestExtractLearnedBlock:
    """Tests for extract_learned_block function.

    Contract mandates JSON array. Markdown fallbacks removed.
    """

    def test_json_learned_block(self):
        # Simulate JSONL transcript with JSON LEARNED block in assistant message
        transcript = '{"message": {"role": "assistant", "content": "LEARNED: [{\\"type\\": \\"decision\\", \\"trigger\\": \\"chose REST\\", \\"resolution\\": \\"simpler\\"}]"}}'
        learned = extract_learned_block(transcript)
        assert len(learned) == 1
        assert learned[0]["type"] == "decision"
        assert learned[0]["trigger"] == "chose REST"

    def test_markdown_returns_empty(self):
        # Markdown format is no longer supported - returns empty
        transcript = '''
### LEARNED
- Decision: We chose REST over GraphQL because simpler
'''
        learned = extract_learned_block(transcript)
        assert learned == []

    def test_no_learned_block(self):
        transcript = "Plan without learned section"
        learned = extract_learned_block(transcript)
        assert learned == []


class TestExtractCandidates:
    """Tests for extract_*_candidates functions."""

    def test_builder_with_learned_field(self):
        # JSONL format with assistant message containing learned field
        transcript = '{"message": {"role": "assistant", "content": "learned: {\\"type\\": \\"pattern\\", \\"trigger\\": \\"When X\\", \\"resolution\\": \\"Do Y\\"}\\nDELIVERED: Done"}}'
        candidates = extract_builder_candidates(transcript)
        assert len(candidates) >= 1
        structured = [c for c in candidates if c["source"] == "builder:structured"]
        assert len(structured) == 1
        assert structured[0]["type"] == "pattern"

    def test_explorer_findings_json(self):
        # JSON format (contract-compliant)
        transcript = '{"message": {"role": "assistant", "content": "{\\"scope\\": \\"src\\", \\"status\\": \\"success\\", \\"findings\\": [{\\"file\\": \\"src/auth.py\\", \\"what\\": \\"JWT tokens\\"}]}"}}'
        candidates = extract_explorer_candidates(transcript)
        assert len(candidates) == 1
        assert candidates[0]["type"] == "fact"
        assert candidates[0]["source"] == "explorer:findings"

    def test_planner_learned_json(self):
        # JSON format (contract-compliant)
        transcript = '{"message": {"role": "assistant", "content": "LEARNED: [{\\"type\\": \\"decision\\", \\"trigger\\": \\"chose SQLite\\", \\"resolution\\": \\"simplicity\\"}]"}}'
        candidates = extract_planner_candidates(transcript)
        assert len(candidates) == 1
        assert candidates[0]["type"] == "decision"


class TestProcessTranscript:
    """Tests for process_transcript function."""

    def test_builder_transcript(self):
        # JSONL format with assistant message
        # Note: DELIVERED must appear in raw string for extract_outcome regex
        transcript = '{"message": {"role": "assistant", "content": "learned: {\\"type\\": \\"pattern\\", \\"trigger\\": \\"X\\", \\"resolution\\": \\"Y\\"}"}}\n{"message": {"role": "assistant", "content": "DELIVERED: Added feature"}}'
        entry = process_transcript(
            agent_id="agent-123",
            agent_type="helix:helix-builder",
            transcript=transcript,
        )

        assert entry["agent_id"] == "agent-123"
        assert entry["agent_type"] == "helix:helix-builder"
        assert entry["outcome"] == "delivered"
        assert len(entry["candidates"]) >= 1

    def test_explorer_transcript(self):
        # JSON format (contract-compliant)
        transcript = '{"message": {"role": "assistant", "content": "{\\"scope\\": \\"src\\", \\"status\\": \\"success\\", \\"findings\\": [{\\"file\\": \\"src/auth.py\\", \\"what\\": \\"auth service\\"}]}"}}'
        entry = process_transcript(
            agent_id="agent-456",
            agent_type="helix:helix-explorer",
            transcript=transcript,
        )

        assert entry["outcome"] == "delivered"
        assert len(entry["candidates"]) >= 1

    @patch("hooks.extract_learning.get_injection_state")
    def test_includes_injected_memories(self, mock_get_state):
        mock_get_state.return_value = {
            "injected_memories": ["mem-1", "mem-2"],
        }

        entry = process_transcript(
            agent_id="agent-789",
            agent_type="helix:helix-builder",
            transcript="DELIVERED: Done",
            tool_use_id="tool-123",
        )

        assert entry["injected_memories"] == ["mem-1", "mem-2"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
