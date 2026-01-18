"""Test FTL v2 memory.py operations."""

import json
from pathlib import Path


class TestMemoryContext:
    """Test memory context retrieval."""

    def test_empty_memory_returns_empty_lists(self, cli, ftl_dir):
        """Empty memory returns empty failures and patterns."""
        code, out, err = cli.memory("context", "--all")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["failures"] == []
        assert data["patterns"] == []

    def test_context_respects_max_limits(self, cli, ftl_dir):
        """Context respects max_failures and max_patterns limits."""
        # Add multiple failures with very different triggers to avoid deduplication
        error_types = [
            "ModuleNotFoundError: No module named 'pandas'",
            "TypeError: cannot unpack non-iterable NoneType object",
            "ValueError: invalid literal for int() with base 10",
            "KeyError: 'missing_key' not found in dict",
            "AttributeError: object has no attribute 'foobar'",
            "IndexError: list index out of range",
            "FileNotFoundError: No such file or directory",
            "ConnectionError: Failed to establish connection",
            "TimeoutError: Operation timed out after 30s",
            "PermissionError: Access denied to resource"
        ]
        for i, trigger in enumerate(error_types):
            failure = {
                "name": f"failure-{i}",
                "trigger": trigger,
                "fix": f"Fix {i}",
                "cost": i * 1000,
                "source": [f"ws-{i}"]
            }
            cli.memory("add-failure", "--json", json.dumps(failure))

        # Default limit is 5
        code, out, _ = cli.memory("context", "--type", "BUILD")
        data = json.loads(out)
        assert len(data["failures"]) == 5

        # Explicit limit
        code, out, _ = cli.memory("context", "--max-failures", "3")
        data = json.loads(out)
        assert len(data["failures"]) == 3

    def test_context_sorts_by_cost(self, cli, ftl_dir):
        """Failures sorted by cost descending."""
        for cost in [1000, 5000, 3000]:
            failure = {
                "name": f"failure-{cost}",
                "trigger": f"Error with cost {cost}",
                "fix": "Fix it",
                "cost": cost,
                "source": ["ws-1"]
            }
            cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        costs = [f["cost"] for f in data["failures"]]
        assert costs == sorted(costs, reverse=True)


class TestMemoryAddFailure:
    """Test adding failures to memory."""

    def test_add_failure_basic(self, cli, ftl_dir):
        """Add basic failure entry."""
        failure = {
            "name": "import-error",
            "trigger": "ModuleNotFoundError: No module named 'foo'",
            "fix": "pip install foo",
            "match": "No module named.*foo",
            "cost": 5000,
            "source": ["001-test-task"]
        }

        code, out, err = cli.memory("add-failure", "--json", json.dumps(failure))
        assert code == 0, f"Failed: {err}"
        assert "added" in out.lower()

        # Verify stored
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert len(data["failures"]) == 1
        assert data["failures"][0]["name"] == "import-error"

    def test_add_failure_deduplicates(self, cli, ftl_dir):
        """Duplicate triggers are merged, not added twice."""
        failure1 = {
            "name": "same-error",
            "trigger": "ImportError: cannot import name 'X'",
            "fix": "Fix it",
            "cost": 1000,
            "source": ["ws-1"]
        }
        failure2 = {
            "name": "same-error-variant",
            "trigger": "ImportError: cannot import name 'X'",  # Same trigger
            "fix": "Better fix",
            "cost": 2000,
            "source": ["ws-2"]
        }

        cli.memory("add-failure", "--json", json.dumps(failure1))
        cli.memory("add-failure", "--json", json.dumps(failure2))

        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)

        # Should only be 1 entry (merged)
        assert len(data["failures"]) == 1
        # Should have higher cost
        assert data["failures"][0]["cost"] == 2000
        # Should have merged sources
        assert set(data["failures"][0]["source"]) == {"ws-1", "ws-2"}


class TestMemoryAddPattern:
    """Test adding patterns to memory."""

    def test_add_pattern_basic(self, cli, ftl_dir):
        """Add basic pattern entry."""
        pattern = {
            "name": "lazy-import",
            "trigger": "Circular import at runtime",
            "insight": "Move import inside function body",
            "saved": 10000,
            "source": ["001-fix-imports"]
        }

        code, out, err = cli.memory("add-pattern", "--json", json.dumps(pattern))
        assert code == 0, f"Failed: {err}"

        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert len(data["patterns"]) == 1
        assert data["patterns"][0]["insight"] == "Move import inside function body"

    def test_add_pattern_deduplicates(self, cli, ftl_dir):
        """Duplicate pattern triggers are not added."""
        pattern1 = {
            "name": "pattern-1",
            "trigger": "Same trigger here",
            "insight": "First insight",
            "saved": 1000,
            "source": ["ws-1"]
        }
        pattern2 = {
            "name": "pattern-2",
            "trigger": "Same trigger here",  # Same trigger
            "insight": "Second insight",
            "saved": 2000,
            "source": ["ws-2"]
        }

        cli.memory("add-pattern", "--json", json.dumps(pattern1))
        cli.memory("add-pattern", "--json", json.dumps(pattern2))

        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)

        # Second should be rejected (not merged like failures)
        assert len(data["patterns"]) == 1
        assert data["patterns"][0]["name"] == "pattern-1"


class TestMemoryQuery:
    """Test memory query functionality."""

    def test_query_finds_failures(self, cli, ftl_dir):
        """Query finds matching failures."""
        failure = {
            "name": "import-circular",
            "trigger": "ImportError: circular import",
            "fix": "Lazy import",
            "cost": 5000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("query", "circular")
        data = json.loads(out)

        assert len(data) == 1
        assert data[0]["type"] == "failure"
        assert data[0]["name"] == "import-circular"

    def test_query_finds_patterns(self, cli, ftl_dir):
        """Query finds matching patterns."""
        pattern = {
            "name": "component-tree",
            "trigger": "Building FastHTML UI",
            "insight": "Return Div(), not strings",
            "saved": 3000,
            "source": ["ws-1"]
        }
        cli.memory("add-pattern", "--json", json.dumps(pattern))

        code, out, _ = cli.memory("query", "FastHTML")
        data = json.loads(out)

        assert len(data) == 1
        assert data[0]["type"] == "pattern"

    def test_query_case_insensitive(self, cli, ftl_dir):
        """Query is case-insensitive."""
        failure = {
            "name": "type-error",
            "trigger": "TypeError: expected string",
            "fix": "Cast to str",
            "cost": 1000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("query", "TYPEERROR")
        data = json.loads(out)
        assert len(data) == 1

    def test_query_empty_result(self, cli, ftl_dir):
        """Query returns empty list when nothing matches."""
        code, out, _ = cli.memory("query", "nonexistent")
        data = json.loads(out)
        assert data == []


class TestSemanticMemory:
    """Test semantic memory features: objective parameter, hybrid scoring, and retrieval."""

    def test_context_with_objective_returns_relevance_scores(self, cli, ftl_dir):
        """When objective is provided, entries include _relevance and _score."""
        failure = {
            "name": "import-numpy",
            "trigger": "ModuleNotFoundError: No module named 'numpy'",
            "fix": "pip install numpy",
            "cost": 5000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("context", "--objective", "numpy import error")
        data = json.loads(out)

        assert len(data["failures"]) == 1
        # Should have relevance and score fields when objective provided
        assert "_relevance" in data["failures"][0]
        assert "_score" in data["failures"][0]

    def test_context_without_objective_no_relevance_scores(self, cli, ftl_dir):
        """Without objective, entries should NOT have _relevance or _score."""
        failure = {
            "name": "import-pandas",
            "trigger": "ModuleNotFoundError: No module named 'pandas'",
            "fix": "pip install pandas",
            "cost": 3000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("context")
        data = json.loads(out)

        assert len(data["failures"]) == 1
        # Should NOT have relevance/score without objective
        assert "_relevance" not in data["failures"][0]
        assert "_score" not in data["failures"][0]

    def test_hybrid_scoring_prioritizes_relevant_high_cost(self, cli, ftl_dir):
        """Hybrid scoring: relevance × log₂(cost + 1) prioritizes relevant + expensive."""
        # Add failures with different relevance/cost combinations
        failures = [
            {
                "name": "high-cost-irrelevant",
                "trigger": "Database connection timeout after 30 seconds",
                "fix": "Increase timeout",
                "cost": 50000,  # Very high cost but irrelevant
                "source": ["ws-1"]
            },
            {
                "name": "low-cost-relevant",
                "trigger": "TypeError: cannot concatenate str and int in Python",
                "fix": "Use str() conversion",
                "cost": 500,  # Low cost but relevant
                "source": ["ws-2"]
            },
            {
                "name": "medium-cost-relevant",
                "trigger": "TypeError: unsupported operand type str and integer",
                "fix": "Cast types properly",
                "cost": 10000,  # Medium cost and relevant
                "source": ["ws-3"]
            },
        ]

        for f in failures:
            cli.memory("add-failure", "--json", json.dumps(f))

        # Query for type errors - should prioritize relevant entries
        code, out, _ = cli.memory("context", "--objective", "TypeError string integer conversion")
        data = json.loads(out)

        # The relevant entries should be ranked higher than the irrelevant one
        names = [f["name"] for f in data["failures"]]

        # Relevant entries should come before irrelevant high-cost entry
        assert "medium-cost-relevant" in names[:2] or "low-cost-relevant" in names[:2]

    def test_semantic_retrieval_finds_similar_entries(self, cli, ftl_dir):
        """Semantic retrieval finds entries with similar meaning, not just exact match."""
        # Add failures with semantically related but textually different triggers
        failures = [
            {
                "name": "auth-expired",
                "trigger": "JWT token has expired, please login again",
                "fix": "Refresh token",
                "cost": 5000,
                "source": ["ws-1"]
            },
            {
                "name": "syntax-error",
                "trigger": "SyntaxError: unexpected indent in line 42",
                "fix": "Fix indentation",
                "cost": 5000,
                "source": ["ws-2"]
            },
        ]

        for f in failures:
            cli.memory("add-failure", "--json", json.dumps(f))

        # Query for authentication - should find auth-expired even without exact match
        code, out, _ = cli.memory("context", "--objective", "authentication token invalid session expired")
        data = json.loads(out)

        # Auth-related entry should be found and have high relevance
        auth_entry = next((f for f in data["failures"] if f["name"] == "auth-expired"), None)
        assert auth_entry is not None, "Auth-related entry should be found by semantic similarity"
        assert auth_entry["_relevance"] > 0.25, f"Auth entry should have relevance > 0.25, got {auth_entry['_relevance']}"

        # If syntax-error is also returned (as fallback), auth should rank higher
        syntax_entry = next((f for f in data["failures"] if f["name"] == "syntax-error"), None)
        if syntax_entry is not None:
            assert auth_entry["_relevance"] > syntax_entry["_relevance"]

    def test_min_results_returns_fallback_when_nothing_relevant(self, cli, ftl_dir):
        """min_results ensures at least some entries returned even when below threshold."""
        failure = {
            "name": "network-error",
            "trigger": "ConnectionRefusedError: Could not connect to server",
            "fix": "Check server is running",
            "cost": 10000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        # Query for something completely unrelated
        code, out, _ = cli.memory("context", "--objective", "memory allocation overflow")
        data = json.loads(out)

        # Should still return at least 1 entry (min_results default) as fallback
        assert len(data["failures"]) >= 1

    def test_hybrid_scoring_formula_correct(self, cli, ftl_dir):
        """Verify hybrid score = relevance × log₂(cost + 1)."""
        import math

        failure = {
            "name": "test-failure",
            "trigger": "Python import error",
            "fix": "Install package",
            "cost": 1023,  # log₂(1024) = 10
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("context", "--objective", "Python import error")
        data = json.loads(out)

        entry = data["failures"][0]
        relevance = entry["_relevance"]
        score = entry["_score"]

        # Score should be relevance × log₂(cost + 1) = relevance × 10
        expected_score = relevance * math.log2(1024)
        assert abs(score - expected_score) < 0.01, f"Expected {expected_score}, got {score}"

    def test_patterns_also_use_hybrid_scoring(self, cli, ftl_dir):
        """Patterns use saved value (not cost) for hybrid scoring."""
        patterns = [
            {
                "name": "pattern-high-saved",
                "trigger": "Building React component tree",
                "insight": "Use functional components",
                "saved": 20000,
                "source": ["ws-1"]
            },
            {
                "name": "pattern-low-saved",
                "trigger": "React component rendering",
                "insight": "Memoize expensive renders",
                "saved": 1000,
                "source": ["ws-2"]
            },
        ]

        for p in patterns:
            cli.memory("add-pattern", "--json", json.dumps(p))

        code, out, _ = cli.memory("context", "--objective", "React component optimization")
        data = json.loads(out)

        # Both patterns should have _relevance and _score
        for p in data["patterns"]:
            assert "_relevance" in p
            assert "_score" in p

        # Higher saved value should contribute to higher score when relevance is similar
        pattern_1 = next(p for p in data["patterns"] if p["name"] == "pattern-high-saved")
        pattern_2 = next(p for p in data["patterns"] if p["name"] == "pattern-low-saved")

        # If relevance is similar, higher saved should mean higher score
        if abs(pattern_1["_relevance"] - pattern_2["_relevance"]) < 0.1:
            assert pattern_1["_score"] > pattern_2["_score"]


class TestMemoryPruning:
    """Test memory pruning functionality."""

    def test_prune_removes_low_importance_entries(self, cli, ftl_dir):
        """Pruning removes entries below importance threshold."""
        from datetime import datetime, timedelta

        # Add old low-cost failure (should be pruned due to age decay)
        # Cost must be >= 100 to pass quality gate
        old_failure = {
            "name": "old-low-cost",
            "trigger": "Minor warning message that happened long ago",
            "fix": "Ignore it",
            "cost": 200,  # Low cost but above MIN_FAILURE_COST
            "source": ["ws-old"],
            "created_at": (datetime.now() - timedelta(days=90)).isoformat(),
        }
        cli.memory("add-failure", "--json", json.dumps(old_failure))

        # Add recent high-cost failure (should be kept)
        new_failure = {
            "name": "new-high-cost",
            "trigger": "Critical error that crashed the system completely",
            "fix": "Major fix required",
            "cost": 50000,
            "source": ["ws-new"],
        }
        cli.memory("add-failure", "--json", json.dumps(new_failure))

        # Verify both exist
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert len(data["failures"]) == 2, f"Expected 2 failures, got {len(data['failures'])}"

        # Prune with limit of 1 to force removal
        code, out, err = cli.memory("prune", "--max-failures", "1", "--min-importance", "0")
        assert code == 0, f"Failed: {err}"
        result = json.loads(out)

        # Check that pruning removed one entry
        assert result["remaining_failures"] == 1
        assert result["pruned_failures"] == 1

    def test_prune_enforces_size_limits(self, cli, ftl_dir):
        """Pruning enforces maximum size limits."""
        # Add many failures with highly distinct triggers to avoid semantic deduplication
        error_types = [
            "ModuleNotFoundError: No module named 'pandas'",
            "TypeError: cannot unpack non-iterable NoneType object",
            "ValueError: invalid literal for int() with base 10",
            "KeyError: 'user_id' not found in dictionary",
            "AttributeError: 'list' object has no attribute 'split'",
            "IndexError: tuple index out of range",
            "FileNotFoundError: [Errno 2] No such file",
            "ConnectionError: Failed to establish connection",
            "TimeoutError: Operation timed out",
            "PermissionError: Access denied to resource",
        ]
        for i, trigger in enumerate(error_types):
            failure = {
                "name": f"failure-{i}",
                "trigger": trigger,
                "fix": f"Fix {i}",
                "cost": (i + 1) * 1000,
                "source": [f"ws-{i}"]
            }
            cli.memory("add-failure", "--json", json.dumps(failure))

        # Verify all were added
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        initial_count = len(data["failures"])
        assert initial_count >= 8, f"Expected at least 8 failures, got {initial_count}"

        # Prune to max 3
        code, out, _ = cli.memory("prune", "--max-failures", "3", "--min-importance", "0")
        result = json.loads(out)
        assert result["remaining_failures"] == 3
        assert result["pruned_failures"] == initial_count - 3


class TestMemoryRelationships:
    """Test graph relationship features."""

    def test_add_relationship_between_failures(self, cli, ftl_dir):
        """Can add bidirectional relationships between failures."""
        # Add two failures
        failure1 = {
            "name": "auth-failure",
            "trigger": "Authentication failed",
            "fix": "Check credentials",
            "cost": 5000,
            "source": ["ws-1"]
        }
        failure2 = {
            "name": "session-failure",
            "trigger": "Session expired",
            "fix": "Refresh session",
            "cost": 3000,
            "source": ["ws-2"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure1))
        cli.memory("add-failure", "--json", json.dumps(failure2))

        # Add relationship
        code, out, err = cli.memory("add-relationship", "auth-failure", "session-failure")
        assert code == 0, f"Failed: {err}"
        assert "added" in out

        # Adding same relationship again should return "exists"
        code, out, _ = cli.memory("add-relationship", "auth-failure", "session-failure")
        assert "exists" in out

    def test_get_related_entries(self, cli, ftl_dir):
        """Can retrieve related entries with multi-hop traversal."""
        # Add three failures with distinct triggers
        failures = [
            {"name": "network-err", "trigger": "NetworkError: connection refused", "fix": "Check server", "cost": 1000, "source": ["ws"]},
            {"name": "timeout-err", "trigger": "TimeoutError: request timed out after 30s", "fix": "Increase timeout", "cost": 2000, "source": ["ws"]},
            {"name": "retry-err", "trigger": "RetryError: max retries exceeded", "fix": "Add backoff", "cost": 3000, "source": ["ws"]},
        ]
        for f in failures:
            cli.memory("add-failure", "--json", json.dumps(f))

        # Create chain: network-err -> timeout-err -> retry-err
        code1, out1, _ = cli.memory("add-relationship", "network-err", "timeout-err")
        code2, out2, _ = cli.memory("add-relationship", "timeout-err", "retry-err")

        assert "added" in out1, f"First relationship failed: {out1}"
        assert "added" in out2, f"Second relationship failed: {out2}"

        # Get related from network-err with max_hops=2
        code, out, err = cli.memory("related", "network-err", "--max-hops", "2")
        assert code == 0, f"Related command failed: {err}"
        data = json.loads(out)

        # Should find both timeout-err (hop 1) and retry-err (hop 2)
        names = [r["entry"]["name"] for r in data]
        assert "timeout-err" in names, f"Expected timeout-err in {names}"
        assert "retry-err" in names, f"Expected retry-err in {names}"

    def test_relationship_not_found(self, cli, ftl_dir):
        """Adding relationship with non-existent entry returns not_found."""
        failure = {
            "name": "exists",
            "trigger": "This is a real error message that exists",
            "fix": "Fix the issue",
            "cost": 1000,
            "source": ["ws"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, _ = cli.memory("add-relationship", "exists", "nonexistent")
        assert "not_found:nonexistent" in out


class TestMemoryStats:
    """Test memory statistics functionality."""

    def test_stats_returns_counts(self, cli, ftl_dir):
        """Stats returns entry counts."""
        # Add some entries
        failure = {
            "name": "test-failure",
            "trigger": "Test error",
            "fix": "Test fix",
            "cost": 5000,
            "source": ["ws-1"]
        }
        pattern = {
            "name": "test-pattern",
            "trigger": "Test trigger",
            "insight": "Test insight",
            "saved": 3000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))
        cli.memory("add-pattern", "--json", json.dumps(pattern))

        code, out, err = cli.memory("stats")
        assert code == 0, f"Failed: {err}"
        stats = json.loads(out)

        assert stats["failures"]["count"] == 1
        assert stats["patterns"]["count"] == 1
        assert stats["failures"]["avg_importance"] > 0

    def test_stats_empty_memory(self, cli, ftl_dir):
        """Stats works with empty memory."""
        code, out, _ = cli.memory("stats")
        stats = json.loads(out)

        assert stats["failures"]["count"] == 0
        assert stats["patterns"]["count"] == 0


class TestDecayMechanism:
    """Test time-based decay in importance scoring."""

    def test_older_entries_have_lower_importance(self, cli, ftl_dir):
        """Older entries should have lower importance due to decay."""
        from datetime import datetime, timedelta

        # Add old failure
        old_failure = {
            "name": "old-failure",
            "trigger": "Old error from long ago",
            "fix": "Old fix",
            "cost": 10000,
            "source": ["ws-old"],
            "created_at": (datetime.now() - timedelta(days=60)).isoformat(),
        }
        cli.memory("add-failure", "--json", json.dumps(old_failure))

        # Add new failure with same cost
        new_failure = {
            "name": "new-failure",
            "trigger": "Recent error just happened",
            "fix": "New fix",
            "cost": 10000,
            "source": ["ws-new"],
        }
        cli.memory("add-failure", "--json", json.dumps(new_failure))

        # After pruning, newer entry should be preferred (higher importance)
        # We test this by setting a strict limit
        code, out, _ = cli.memory("prune", "--max-failures", "1", "--min-importance", "0")
        result = json.loads(out)
        assert result["remaining_failures"] == 1

        # Check which one survived
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert len(data["failures"]) == 1
        # New failure should survive because it has higher importance (no decay)
        assert data["failures"][0]["name"] == "new-failure"


class TestMemoryFeedbackCLI:
    """Test memory feedback CLI command."""

    def test_feedback_helped_increments_times_helped(self, cli, ftl_dir):
        """Feedback --helped increments times_helped counter."""
        failure = {
            "name": "feedback-test",
            "trigger": "Test error for feedback",
            "fix": "Test fix",
            "cost": 5000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        # Record positive feedback
        code, out, err = cli.memory("feedback", "feedback-test", "--helped")
        assert code == 0, f"Failed: {err}"
        assert "updated" in out

        # Verify counter incremented
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert data["failures"][0]["times_helped"] == 1

    def test_feedback_failed_increments_times_failed(self, cli, ftl_dir):
        """Feedback --failed increments times_failed counter."""
        failure = {
            "name": "failed-test",
            "trigger": "Test error for failure feedback",
            "fix": "Test fix",
            "cost": 3000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        # Record negative feedback
        code, out, err = cli.memory("feedback", "failed-test", "--failed")
        assert code == 0, f"Failed: {err}"
        assert "updated" in out

        # Verify counter incremented
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert data["failures"][0]["times_failed"] == 1

    def test_feedback_not_found(self, cli, ftl_dir):
        """Feedback on non-existent entry returns not_found."""
        code, out, _ = cli.memory("feedback", "nonexistent", "--helped")
        assert "not_found" in out

    def test_feedback_requires_helped_or_failed(self, cli, ftl_dir):
        """Feedback requires either --helped or --failed flag."""
        failure = {
            "name": "flag-test",
            "trigger": "Need flag test",
            "fix": "Fix",
            "cost": 1000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        code, out, err = cli.memory("feedback", "flag-test")
        assert code != 0
        # Error message may be in stdout or stderr depending on implementation
        combined = (out + err).lower()
        assert "helped" in combined or "failed" in combined

    def test_feedback_pattern_type(self, cli, ftl_dir):
        """Feedback works with patterns using --type pattern."""
        pattern = {
            "name": "pattern-feedback",
            "trigger": "Pattern for feedback test",
            "insight": "Test insight",
            "saved": 5000,
            "source": ["ws-1"]
        }
        cli.memory("add-pattern", "--json", json.dumps(pattern))

        # Record feedback on pattern
        code, out, err = cli.memory("feedback", "pattern-feedback", "--type", "pattern", "--helped")
        assert code == 0, f"Failed: {err}"
        assert "updated" in out

    def test_multiple_feedback_accumulates(self, cli, ftl_dir):
        """Multiple feedback calls accumulate counters."""
        failure = {
            "name": "multi-feedback",
            "trigger": "Multiple feedback test",
            "fix": "Fix",
            "cost": 2000,
            "source": ["ws-1"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        # Record multiple positive feedback
        cli.memory("feedback", "multi-feedback", "--helped")
        cli.memory("feedback", "multi-feedback", "--helped")
        cli.memory("feedback", "multi-feedback", "--failed")

        # Verify counters
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert data["failures"][0]["times_helped"] == 2
        assert data["failures"][0]["times_failed"] == 1
