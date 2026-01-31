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
    classify_learning,
    parse_trigger_resolution,
    extract_builder_candidates,
    extract_explorer_candidates,
    extract_planner_candidates,
    process_transcript,
)


class TestExtractLearnedField:
    """Tests for extract_learned_field function."""

    def test_json_format(self):
        transcript = '''
Some work happened.
learned: {"type": "pattern", "trigger": "When X", "resolution": "Do Y"}
More work.
'''
        result = extract_learned_field(transcript)
        assert result is not None
        assert result["type"] == "pattern"
        assert result["trigger"] == "When X"

    def test_quoted_format(self):
        transcript = '''
"learned": {"type": "failure", "trigger": "Error X", "resolution": "Fix Y"}
'''
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
    """Tests for extract_findings_section function."""

    def test_findings_with_bullets(self):
        transcript = '''
## FINDINGS
- Found auth module at src/auth.py
- Database uses PostgreSQL
- API routes in src/api/

## Next Steps
'''
        findings = extract_findings_section(transcript)
        assert len(findings) == 3
        assert "auth module" in findings[0]
        assert "PostgreSQL" in findings[1]

    def test_findings_with_asterisks(self):
        transcript = '''
FINDINGS:
* Item one
* Item two
'''
        findings = extract_findings_section(transcript)
        assert len(findings) == 2

    def test_no_findings(self):
        transcript = "Just some text without findings"
        findings = extract_findings_section(transcript)
        assert findings == []


class TestExtractLearnedBlock:
    """Tests for extract_learned_block function."""

    def test_learned_block(self):
        transcript = '''
### LEARNED
- Decision: We chose REST over GraphQL because simpler
- Pattern: When testing auth, mock the token service
'''
        learned = extract_learned_block(transcript)
        assert len(learned) == 2
        assert "REST over GraphQL" in learned[0]
        assert "mock the token" in learned[1]

    def test_no_learned_block(self):
        transcript = "Plan without learned section"
        learned = extract_learned_block(transcript)
        assert learned == []


class TestClassifyLearning:
    """Tests for classify_learning function."""

    def test_explicit_prefix(self):
        assert classify_learning("Decision: chose X") == "decision"
        assert classify_learning("Pattern: use X") == "pattern"
        assert classify_learning("Convention: always X") == "convention"
        assert classify_learning("Fact: the system X") == "fact"

    def test_heuristics(self):
        assert classify_learning("Always use TypeScript") == "convention"
        assert classify_learning("The build failed because") == "failure"
        assert classify_learning("We decided to use React") == "decision"
        assert classify_learning("When testing, mock services") == "pattern"

    def test_default(self):
        assert classify_learning("Some random text") == "pattern"


class TestParseTriggerResolution:
    """Tests for parse_trigger_resolution function."""

    def test_arrow_separator(self):
        trigger, resolution = parse_trigger_resolution("Error X -> Fix Y")
        assert trigger == "Error X"
        assert resolution == "Fix Y"

    def test_colon_separator(self):
        trigger, resolution = parse_trigger_resolution("Pattern: use mocks")
        assert trigger == "Pattern"
        assert resolution == "use mocks"

    def test_when_pattern(self):
        trigger, resolution = parse_trigger_resolution("When testing auth, mock tokens")
        assert trigger == "When testing auth"
        assert resolution == "mock tokens"

    def test_fallback(self):
        trigger, resolution = parse_trigger_resolution("Just some text")
        assert trigger == "Just some text"
        assert resolution == ""


class TestExtractCandidates:
    """Tests for extract_*_candidates functions."""

    def test_builder_with_learned_field(self):
        transcript = '''
learned: {"type": "pattern", "trigger": "When X", "resolution": "Do Y"}
DELIVERED: Done
'''
        candidates = extract_builder_candidates(transcript)
        assert len(candidates) >= 1
        structured = [c for c in candidates if c["source"] == "builder:structured"]
        assert len(structured) == 1
        assert structured[0]["type"] == "pattern"

    def test_builder_with_inline_notes(self):
        transcript = '''
Learned: When mocking auth services, always isolate the token provider.
DELIVERED: Done
'''
        candidates = extract_builder_candidates(transcript)
        inline = [c for c in candidates if c["source"] == "builder:inline"]
        assert len(inline) >= 1

    def test_explorer_findings(self):
        transcript = '''
## FINDINGS
- The auth module uses JWT tokens stored in Redis
- All API routes go through middleware
'''
        candidates = extract_explorer_candidates(transcript)
        assert len(candidates) == 2
        assert all(c["type"] == "fact" for c in candidates)
        assert all(c["source"] == "explorer:findings" for c in candidates)

    def test_planner_learned(self):
        transcript = '''
### LEARNED
- Decision: chose SQLite for simplicity
- Pattern: group related files in same task
'''
        candidates = extract_planner_candidates(transcript)
        assert len(candidates) == 2


class TestProcessTranscript:
    """Tests for process_transcript function."""

    def test_builder_transcript(self):
        transcript = '''
learned: {"type": "pattern", "trigger": "X", "resolution": "Y"}
DELIVERED: Added feature
'''
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
        transcript = '''
## FINDINGS
- Found the auth service
{"status": "success"}
'''
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
