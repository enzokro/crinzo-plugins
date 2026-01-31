#!/usr/bin/env python3
"""Tests for prompt_parser module."""

import json
import sys
from pathlib import Path

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from prompt_parser import (
    parse_prompt,
    detect_agent_type,
    extract_explorer_params,
    extract_planner_params,
    extract_builder_params,
    should_inject,
    rebuild_prompt,
    inject_context_into_prompt,
)


class TestParsePrompt:
    """Tests for parse_prompt function."""

    def test_simple_fields(self):
        prompt = """SCOPE: src/api/
OBJECTIVE: Find auth flow"""
        result = parse_prompt(prompt)
        assert result["scope"] == "src/api/"
        assert result["objective"] == "Find auth flow"

    def test_multiline_field(self):
        prompt = """OBJECTIVE: Find the authentication flow
  and understand how tokens are handled
  across multiple requests
SCOPE: src/"""
        result = parse_prompt(prompt)
        assert "authentication flow" in result["objective"]
        assert "multiple requests" in result["objective"]
        assert result["scope"] == "src/"

    def test_json_field(self):
        prompt = 'RELEVANT_FILES: ["src/api.py", "src/auth.py"]'
        result = parse_prompt(prompt)
        assert result["relevant_files"] == ["src/api.py", "src/auth.py"]

    def test_int_field(self):
        prompt = "MEMORY_LIMIT: 7"
        result = parse_prompt(prompt)
        assert result["memory_limit"] == 7

    def test_invalid_json_preserved_as_string(self):
        prompt = "RELEVANT_FILES: not valid json"
        result = parse_prompt(prompt)
        assert result["relevant_files"] == "not valid json"

    def test_unrecognized_fields_ignored(self):
        prompt = """SCOPE: src/
UNKNOWN_FIELD: value"""
        result = parse_prompt(prompt)
        assert result["scope"] == "src/"
        assert "unknown_field" not in result

    def test_empty_prompt(self):
        result = parse_prompt("")
        assert result == {}

    def test_none_prompt(self):
        result = parse_prompt(None)
        assert result == {}


class TestDetectAgentType:
    """Tests for detect_agent_type function."""

    def test_explorer_prompt(self):
        prompt = """SCOPE: src/api/
FOCUS: route handlers
OBJECTIVE: Find endpoints"""
        assert detect_agent_type(prompt) == "explorer"

    def test_planner_prompt(self):
        prompt = """OBJECTIVE: Add auth
EXPLORATION: {"findings": []}"""
        assert detect_agent_type(prompt) == "planner"

    def test_builder_prompt(self):
        prompt = """TASK_ID: 3
TASK: 003: impl-auth
OBJECTIVE: Add login button"""
        assert detect_agent_type(prompt) == "builder"

    def test_unknown_prompt(self):
        prompt = "Just some text"
        assert detect_agent_type(prompt) is None


class TestExtractParams:
    """Tests for extract_*_params functions."""

    def test_explorer_params(self):
        prompt = """SCOPE: src/api/
FOCUS: handlers
OBJECTIVE: Find auth"""
        params = extract_explorer_params(prompt)
        assert params["scope"] == "src/api/"
        assert params["focus"] == "handlers"
        assert params["objective"] == "Find auth"

    def test_planner_params(self):
        prompt = """OBJECTIVE: Add auth
EXPLORATION: {"files": ["src/auth.py"]}"""
        params = extract_planner_params(prompt)
        assert params["objective"] == "Add auth"
        assert params["exploration"] == {"files": ["src/auth.py"]}

    def test_builder_params_full(self):
        prompt = """TASK_ID: 3
TASK: 003: impl-auth
OBJECTIVE: Add login button
VERIFY: npm test
RELEVANT_FILES: ["src/Header.tsx"]
LINEAGE: [{"seq": "001", "slug": "setup", "delivered": "Done"}]
WARNING: Check token handling
MEMORY_LIMIT: 7"""
        params = extract_builder_params(prompt)
        assert params["task_id"] == 3
        assert params["task"] == "003: impl-auth"
        assert params["objective"] == "Add login button"
        assert params["verify"] == "npm test"
        assert params["relevant_files"] == ["src/Header.tsx"]
        assert len(params["lineage"]) == 1
        assert params["warning"] == "Check token handling"
        assert params["memory_limit"] == 7

    def test_builder_params_minimal(self):
        prompt = """TASK: simple task
OBJECTIVE: do something"""
        params = extract_builder_params(prompt)
        assert params["task"] == "simple task"
        assert params["objective"] == "do something"
        assert params["relevant_files"] == []
        assert params["lineage"] == []
        assert params["warning"] is None
        assert params["memory_limit"] == 5  # default


class TestShouldInject:
    """Tests for should_inject function."""

    def test_no_flag(self):
        prompt = "SCOPE: src/"
        assert should_inject(prompt) is True

    def test_flag_true(self):
        prompt = """SCOPE: src/
NO_INJECT: true"""
        assert should_inject(prompt) is False

    def test_flag_yes(self):
        prompt = """SCOPE: src/
NO_INJECT: yes"""
        assert should_inject(prompt) is False

    def test_flag_1(self):
        prompt = """SCOPE: src/
NO_INJECT: 1"""
        assert should_inject(prompt) is False

    def test_flag_false(self):
        prompt = """SCOPE: src/
NO_INJECT: false"""
        assert should_inject(prompt) is True


class TestRebuildPrompt:
    """Tests for rebuild_prompt function."""

    def test_simple_rebuild(self):
        fields = {"scope": "src/", "objective": "Find auth"}
        result = rebuild_prompt(fields)
        assert "SCOPE: src/" in result
        assert "OBJECTIVE: Find auth" in result

    def test_json_field_rebuild(self):
        fields = {"relevant_files": ["a.py", "b.py"]}
        result = rebuild_prompt(fields)
        assert 'RELEVANT_FILES: ["a.py", "b.py"]' in result

    def test_preserve_order(self):
        fields = {"objective": "X", "scope": "Y"}
        result = rebuild_prompt(fields, preserve_order=["scope", "objective"])
        lines = result.split("\n")
        assert lines[0].startswith("SCOPE:")
        assert lines[1].startswith("OBJECTIVE:")


class TestInjectContext:
    """Tests for inject_context_into_prompt function."""

    def test_prepend(self):
        prompt = "SCOPE: src/"
        context = "# MEMORY CONTEXT\n- Fact 1"
        result = inject_context_into_prompt(prompt, context, position="prepend")
        assert result.startswith("# MEMORY CONTEXT")
        assert "---" in result
        assert "SCOPE: src/" in result

    def test_append(self):
        prompt = "SCOPE: src/"
        context = "# MEMORY CONTEXT\n- Fact 1"
        result = inject_context_into_prompt(prompt, context, position="append")
        assert result.startswith("SCOPE: src/")
        assert result.endswith("- Fact 1")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
