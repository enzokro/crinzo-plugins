"""Tests for lib/extraction.py - insight extraction from transcripts."""

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


class TestDerivedInsightFlag:
    """Tests for derived insight marker."""

    def test_derived_insight_has_derived_flag(self):
        """BLOCKED-fallback insights have derived=True."""
        transcript = '''
        TASK: Fix database
        OBJECTIVE: Repair connection pooling
        BLOCKED: Schema migration conflict with existing data
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert result.get("derived") is True

    def test_explicit_insight_no_derived_flag(self):
        """Explicit INSIGHT: extractions do NOT have derived flag."""
        transcript = '''
        DELIVERED: Fixed the issue
        INSIGHT: {"content": "When importing fails, check sys.path first because module resolution depends on it", "tags": ["python"]}
        '''
        result = extract_insight(transcript)

        assert result is not None
        assert "derived" not in result


class TestExtractInsightPreExtracted:
    """Tests for extract_insight with pre-extracted data (avoids re-scanning)."""

    def test_blocked_with_pre_extracted_parts(self):
        """Derive insight from pre-extracted summary_parts + task_parts."""
        transcript = "BLOCKED: Schema migration conflict"
        result = extract_insight(
            transcript,
            outcome="blocked",
            summary_parts=["Schema migration conflict"],
            task_parts=["Repair connection pooling"]
        )

        assert result is not None
        assert "derived" in result.get("tags", [])
        assert "Schema migration conflict" in result["content"]
        assert "Repair connection pooling" in result["content"]

    def test_delivered_with_outcome_skips_fallback(self):
        """Delivered outcome with pre-extracted data skips BLOCKED fallback entirely."""
        transcript = "DELIVERED: Done\nBLOCKED: This should not trigger fallback"
        result = extract_insight(
            transcript,
            outcome="delivered",
            summary_parts=["Done"],
            task_parts=["Build feature"]
        )

        # No explicit INSIGHT: line, and outcome is delivered → no derived insight
        assert result is None

    def test_pre_extracted_matches_full_scan(self):
        """Pre-extracted path produces same result as full transcript scan for BLOCKED."""
        transcript = '''
        TASK: Fix database
        OBJECTIVE: Repair connection pooling
        BLOCKED: Schema migration conflict with existing data
        '''

        # Full scan (backward compat)
        result_full = extract_insight(transcript)

        # Pre-extracted
        result_pre = extract_insight(
            transcript,
            outcome="blocked",
            summary_parts=["Schema migration conflict with existing data"],
            task_parts=["Fix database", "Repair connection pooling"]
        )

        assert result_full is not None
        assert result_pre is not None
        assert result_full["content"] == result_pre["content"]
        assert result_full["tags"] == result_pre["tags"]


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


class TestLastMatchWins:
    """Tests for last-match-wins outcome parsing."""

    def test_last_delivered_wins_over_earlier_blocked(self):
        """When BLOCKED appears in context and DELIVERED at end, DELIVERED wins."""
        transcript = '''
        PARENT_DELIVERIES:
        BLOCKED: Earlier task failed
        The actual builder output:
        DELIVERED: Successfully implemented the feature
        '''
        assert extract_outcome(transcript) == "delivered"

        result = process_completion(transcript)
        assert result["outcome"] == "delivered"

    def test_last_blocked_wins_over_earlier_delivered(self):
        """Agent recovered from initial success claim to report blocking."""
        transcript = '''
        DELIVERED: Thought it was done
        Actually found an issue
        BLOCKED: Tests are failing after the change
        '''
        assert extract_outcome(transcript) == "blocked"

        result = process_completion(transcript)
        assert result["outcome"] == "blocked"

    def test_injected_context_blocked_does_not_override(self):
        """BLOCKED in injected insight context doesn't override agent's DELIVERED."""
        transcript = '''
        INSIGHTS (from past experience):
          - [35%] When attempting 'fix auth': blocked by missing env vars
        INJECTED: ["insight-1"]
        TASK: Fix the login flow
        DELIVERED: Fixed login by adding proper token refresh
        '''
        result = process_completion(transcript)
        assert result["outcome"] == "delivered"


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
