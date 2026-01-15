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
