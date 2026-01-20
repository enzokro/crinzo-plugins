"""Test FTL decision_parser module - plan output parsing."""

import json
import sys
from pathlib import Path

import pytest


class TestDecisionDetection:
    """Test detect_decision function."""

    def test_detect_proceed(self, decision_parser_module):
        """Detect PROCEED decision from planner output."""
        content = """
### Confidence: PROCEED

## Campaign: Add user authentication

### Analysis
The plan is ready.

```json
{"objective": "Test objective", "tasks": []}
```
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "PROCEED"

    def test_detect_clarify(self, decision_parser_module):
        """Detect CLARIFY decision from planner output."""
        content = """
### Confidence: CLARIFY

## Blocking Questions
1. Should authentication use OAuth or JWT?
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "CLARIFY"

    def test_detect_confirm(self, decision_parser_module):
        """Detect CONFIRM decision from planner output."""
        content = """
### Confidence: CONFIRM

## Selection Required

You mentioned both adding authentication and updating the database schema.
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "CONFIRM"

    def test_detect_unknown_when_no_marker(self, decision_parser_module):
        """Return UNKNOWN when no confidence marker found."""
        content = """
This is some text without any confidence marker.
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "UNKNOWN"


class TestPlanExtraction:
    """Test JSON plan extraction from markdown."""

    def test_extract_json_block(self, decision_parser_module):
        """Extract JSON plan from fenced code block."""
        content = """
### Confidence: PROCEED

```json
{
    "objective": "Test objective",
    "campaign": "test-campaign",
    "tasks": [
        {"seq": "001", "slug": "task-1", "type": "SPEC", "delta": ["test.py"], "verify": "pytest", "budget": 3}
    ]
}
```
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "PROCEED"
        plan = result.get("plan") or result.get("plan_json")
        assert plan is not None
        assert plan["objective"] == "Test objective"

    def test_malformed_json_handled(self, decision_parser_module):
        """Malformed JSON doesn't crash."""
        content = """
### Confidence: PROCEED

```json
{not valid json
```
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "PROCEED"


class TestValidatePlan:
    """Test validate_plan function."""

    def test_valid_plan(self, decision_parser_module):
        """Valid plan passes validation."""
        plan = {
            "objective": "Test objective",
            "campaign": "test-campaign",
            "tasks": [
                {
                    "seq": "001",
                    "slug": "task-1",
                    "type": "SPEC",
                    "delta": ["test.py"],
                    "verify": "pytest",
                    "budget": 3,
                    "depends": "none"
                }
            ]
        }

        result = decision_parser_module.validate_plan(plan)

        assert result["valid"] is True
        assert len(result.get("errors", [])) == 0

    def test_missing_objective(self, decision_parser_module):
        """Plan without objective is invalid."""
        plan = {
            "tasks": [{"seq": "001", "slug": "x", "delta": [], "verify": "", "budget": 3}]
        }

        result = decision_parser_module.validate_plan(plan)

        assert result["valid"] is False

    def test_missing_tasks(self, decision_parser_module):
        """Plan without tasks is invalid."""
        plan = {
            "objective": "Test"
        }

        result = decision_parser_module.validate_plan(plan)

        assert result["valid"] is False

    def test_empty_tasks(self, decision_parser_module):
        """Plan with empty tasks array is invalid."""
        plan = {
            "objective": "Test",
            "tasks": []
        }

        result = decision_parser_module.validate_plan(plan)

        assert result["valid"] is False


class TestQuestionExtraction:
    """Test extracting questions from CLARIFY output."""

    def test_extract_numbered_questions(self, decision_parser_module):
        """Extract numbered questions from content."""
        content = """
### Confidence: CLARIFY

## Blocking Questions
1. What authentication method should we use?
2. Should sessions persist across browser restarts?
"""
        result = decision_parser_module.detect_decision(content)

        assert result["decision"] == "CLARIFY"
        questions = result.get("questions", [])

        # Should extract some questions
        assert len(questions) >= 1
