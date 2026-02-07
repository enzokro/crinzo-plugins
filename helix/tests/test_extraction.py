"""Tests for lib/extraction.py - insight extraction from transcripts."""

import pytest
from lib.extraction import extract_insight, extract_outcome, extract_injected_names, process_completion


class TestExtractInsight:
    """Tests for extract_insight function."""

    def test_extract_explicit_insight(self):
        """Extract explicitly formatted INSIGHT line."""
        transcript = '''
        TASK: Fix imports
        OBJECTIVE: Make imports work
        DELIVERED: Fixed the import issue
        INSIGHT: {"content": "When importing fails, check sys.path first", "tags": ["python"]}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "sys.path" in result["content"]
        assert "python" in result["tags"]

    def test_extract_insight_lowercase(self):
        """Handle lowercase insight marker."""
        transcript = '''
        delivered: Success
        insight: {"content": "Always validate input before processing", "tags": ["validation"]}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "validate input" in result["content"]

    def test_extract_insight_no_tags(self):
        """Handle insight without tags."""
        transcript = '''
        DELIVERED: Done
        INSIGHT: {"content": "When X happens, do Y because Z"}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert result["tags"] == []

    def test_delivered_without_insight_returns_none(self):
        """DELIVERED without explicit INSIGHT returns None (no derived noise)."""
        transcript = '''
        TASK: Implement login
        OBJECTIVE: Add user authentication
        DELIVERED: Added OAuth2 login flow with token refresh
        '''
        result = extract_insight(transcript)

        assert result is None

    def test_fallback_to_blocked(self):
        """Derive insight from BLOCKED when no explicit INSIGHT."""
        transcript = '''
        TASK: Fix database
        OBJECTIVE: Repair connection pooling
        BLOCKED: Schema migration conflict with existing data
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "failure" in result["tags"]
        assert "BLOCKED" in result["content"] or "blocked" in result["content"].lower()

    def test_no_insight_returns_none(self):
        """Return None when no insight can be extracted."""
        transcript = '''
        Just some random text
        Without any markers
        '''
        result = extract_insight(transcript)

        assert result is None

    def test_rejects_short_content(self):
        """Reject insights with too-short content."""
        transcript = '''
        INSIGHT: {"content": "Short", "tags": []}
        '''
        result = extract_insight(transcript)

        assert result is None

    def test_extract_insight_nested_braces(self):
        """INSIGHT with } in content string is not truncated."""
        transcript = '''
        DELIVERED: Fixed config parsing
        INSIGHT: {"content": "When {config} is missing from the environment, fall back to defaults", "tags": ["config"]}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "{config}" in result["content"]
        assert "config" in result["tags"]

    def test_extract_insight_nested_json(self):
        """INSIGHT with nested JSON objects in metadata."""
        transcript = '''
        DELIVERED: Done
        INSIGHT: {"content": "When deploying to production, validate all env vars first because missing vars cause silent failures", "tags": ["deploy"], "meta": {"source": "wave-3"}}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "env vars" in result["content"]
        assert "deploy" in result["tags"]


class TestExtractOutcome:
    """Tests for extract_outcome function."""

    def test_delivered_outcome(self):
        """Detect DELIVERED outcome."""
        transcript = "DELIVERED: Task completed successfully"
        assert extract_outcome(transcript) == "delivered"

    def test_blocked_outcome(self):
        """Detect BLOCKED outcome."""
        transcript = "BLOCKED: Could not proceed due to missing dependency"
        assert extract_outcome(transcript) == "blocked"

    def test_unknown_outcome(self):
        """Return unknown when no outcome marker."""
        transcript = "Some text without outcome markers"
        assert extract_outcome(transcript) == "unknown"

    def test_plan_complete_outcome(self):
        """Detect PLAN_COMPLETE outcome."""
        transcript = "PLAN_COMPLETE: 5 tasks created"
        assert extract_outcome(transcript) == "plan_complete"

    def test_case_insensitive(self):
        """Handle case variations."""
        assert extract_outcome("delivered: done") == "delivered"
        assert extract_outcome("Blocked: failed") == "blocked"
        assert extract_outcome("plan_complete: done") == "plan_complete"


class TestExtractInjectedNames:
    """Tests for extract_injected_names function."""

    def test_extract_injected_array(self):
        """Extract JSON array of injected names."""
        transcript = '''
        TASK: Do something
        INJECTED: ["insight-1", "insight-2", "insight-3"]
        '''
        result = extract_injected_names(transcript)

        assert result == ["insight-1", "insight-2", "insight-3"]

    def test_empty_array(self):
        """Handle empty injected array."""
        transcript = 'INJECTED: []'
        result = extract_injected_names(transcript)

        assert result == []

    def test_no_injected_line(self):
        """Return empty list when no INJECTED line."""
        transcript = "No injected line here"
        result = extract_injected_names(transcript)

        assert result == []

    def test_malformed_json(self):
        """Handle malformed JSON gracefully."""
        transcript = 'INJECTED: [not valid json'
        result = extract_injected_names(transcript)

        assert result == []


class TestProcessCompletion:
    """Tests for process_completion function."""

    def test_full_completion(self):
        """Process complete transcript with all fields."""
        transcript = '''
        TASK: Fix authentication
        OBJECTIVE: Add token refresh
        DELIVERED: Implemented refresh token flow
        INSIGHT: {"content": "When tokens expire, use refresh tokens because they reduce login friction", "tags": ["auth"]}
        INJECTED: ["auth-pattern-1", "token-insight-2"]
        '''
        result = process_completion(transcript)

        assert result["outcome"] == "delivered"
        assert result["insight"] is not None
        assert "refresh tokens" in result["insight"]["content"]
        assert result["injected"] == ["auth-pattern-1", "token-insight-2"]

    def test_minimal_completion(self):
        """Process minimal transcript with just outcome."""
        transcript = "DELIVERED: Done"
        result = process_completion(transcript)

        assert result["outcome"] == "delivered"
        assert result["injected"] == []

    def test_blocked_completion(self):
        """Process blocked completion."""
        transcript = '''
        BLOCKED: Tests failing
        INJECTED: ["bad-advice-1"]
        '''
        result = process_completion(transcript)

        assert result["outcome"] == "blocked"
        assert "bad-advice-1" in result["injected"]

    def test_planner_completion(self):
        """Process planner completion with PLAN_COMPLETE outcome."""
        transcript = '''
        OBJECTIVE: Design authentication system
        PLAN_COMPLETE: 5 tasks created in DAG
        INSIGHT: {"content": "When planning auth systems, separate token management from user management because they evolve independently", "tags": ["planning"]}
        INJECTED: ["auth-insight-1"]
        '''
        result = process_completion(transcript)

        assert result["outcome"] == "plan_complete"
        assert result["insight"] is not None
        assert "token management" in result["insight"]["content"]
        assert result["injected"] == ["auth-insight-1"]
