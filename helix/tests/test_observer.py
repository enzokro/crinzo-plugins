"""Tests for observer module."""
import sys
from pathlib import Path

# pytest is optional - tests can run without it
try:
    import pytest
except ImportError:
    pytest = None

# Add lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))

from observer import (
    observe_explorer, observe_planner, observe_builder,
    observe_session, should_store
)


class TestObserveExplorer:
    """Tests for observe_explorer function."""

    def test_extracts_high_relevance_findings(self):
        """High relevance findings should be extracted as facts."""
        output = {
            "scope": "src/auth/",
            "findings": [
                {"file": "src/auth/jwt.py", "what": "JWT token handling", "relevance": "high"},
                {"file": "src/auth/utils.py", "what": "Helper functions", "relevance": "low"},
            ]
        }
        candidates = observe_explorer(output)

        # Should only get the high relevance one
        assert len(candidates) == 1
        assert candidates[0]["type"] == "fact"
        assert "jwt.py" in candidates[0]["trigger"]
        assert candidates[0]["_confidence"] == "medium"  # high relevance = medium confidence

    def test_extracts_critical_with_high_confidence(self):
        """Critical findings should have high confidence."""
        output = {
            "scope": "src/",
            "findings": [
                {"file": "src/main.py", "what": "Entry point", "relevance": "critical"},
            ]
        }
        candidates = observe_explorer(output)

        assert len(candidates) == 1
        assert candidates[0]["_confidence"] == "high"

    def test_extracts_framework_detection(self):
        """Framework detection should be stored as fact."""
        output = {
            "scope": "src/",
            "findings": [],
            "framework": {"detected": "FastAPI", "confidence": "HIGH", "evidence": "Found main.py with FastAPI imports"}
        }
        candidates = observe_explorer(output)

        assert len(candidates) == 1
        assert candidates[0]["type"] == "fact"
        assert "Framework: FastAPI" in candidates[0]["trigger"]

    def test_extracts_patterns_as_conventions(self):
        """Observed patterns should become low-confidence conventions."""
        output = {
            "scope": "src/",
            "findings": [],
            "patterns_observed": ["Repository pattern for data access", "tiny"]
        }
        candidates = observe_explorer(output)

        # Only the long pattern should be extracted
        conventions = [c for c in candidates if c["type"] == "convention"]
        assert len(conventions) == 1
        assert "Repository pattern" in conventions[0]["trigger"]
        assert conventions[0]["_confidence"] == "low"

    def test_skips_empty_findings(self):
        """Findings without file or what should be skipped."""
        output = {
            "scope": "src/",
            "findings": [
                {"file": "", "what": "Something", "relevance": "high"},
                {"file": "src/file.py", "what": "", "relevance": "high"},
            ]
        }
        candidates = observe_explorer(output)
        assert len(candidates) == 0


class TestObservePlanner:
    """Tests for observe_planner function."""

    def test_extracts_decision_patterns(self):
        """Decisions embedded in task text should be extracted."""
        tasks = [
            {
                "subject": "001: setup-auth",
                "description": "Using JWT because it's stateless and scalable",
                "metadata": {}
            }
        ]
        candidates = observe_planner(tasks, {})

        # Should find the "using X because Y" pattern
        decisions = [c for c in candidates if c["type"] == "decision"]
        assert len(decisions) >= 1
        assert any("JWT" in d["trigger"] for d in decisions)

    def test_extracts_chose_over_pattern(self):
        """Should extract 'chose X over Y' patterns."""
        tasks = [
            {
                "subject": "001: setup-db",
                "description": "We chose PostgreSQL over SQLite for production",
                "metadata": {}
            }
        ]
        candidates = observe_planner(tasks, {})

        decisions = [c for c in candidates if c["type"] == "decision"]
        assert len(decisions) >= 1


class TestObserveBuilder:
    """Tests for observe_builder function."""

    def test_creates_evolution_for_delivered(self):
        """Delivered tasks should create evolution entries."""
        task = {"id": "task-001", "subject": "001: add-auth"}
        result = {"status": "delivered", "summary": "Added JWT authentication"}
        files = ["src/auth/jwt.py", "src/auth/middleware.py"]

        candidates = observe_builder(task, result, files)

        evolution = [c for c in candidates if c["type"] == "evolution"]
        assert len(evolution) == 1
        assert "jwt.py" in evolution[0]["resolution"]
        assert evolution[0]["_confidence"] == "high"

    def test_creates_failure_for_blocked(self):
        """Blocked tasks should create failure entries."""
        task = {"id": "task-001", "subject": "001: add-auth"}
        result = {
            "status": "blocked",
            "summary": "Failed to authenticate",
            "error": "Module 'jwt' not found - missing dependency in requirements.txt",
            "tried": "pip install pyjwt"
        }

        candidates = observe_builder(task, result, [])

        failures = [c for c in candidates if c["type"] == "failure"]
        assert len(failures) == 1
        assert "Module 'jwt' not found" in failures[0]["trigger"]
        assert failures[0]["_confidence"] == "high"

    def test_no_evolution_without_files(self):
        """Delivered tasks without file changes shouldn't create evolution."""
        task = {"id": "task-001", "subject": "001: docs"}
        result = {"status": "delivered", "summary": "Updated docs"}

        candidates = observe_builder(task, result, [])

        evolution = [c for c in candidates if c["type"] == "evolution"]
        assert len(evolution) == 0

    def test_extracts_convention_indicators(self):
        """Should extract conventions from summary text."""
        task = {"id": "task-001", "subject": "001: add-auth"}
        result = {
            "status": "delivered",
            "summary": "Following the repository pattern for data access"
        }
        files = ["src/auth/repo.py"]

        candidates = observe_builder(task, result, files)

        conventions = [c for c in candidates if c["type"] == "convention"]
        assert len(conventions) >= 1


class TestObserveSession:
    """Tests for observe_session function."""

    def test_session_summary(self):
        """Should create session summary with task counts."""
        tasks = [
            {"id": "t1", "subject": "001: setup"},
            {"id": "t2", "subject": "002: implement"},
            {"id": "t3", "subject": "003: test"},
        ]
        outcomes = {"t1": "delivered", "t2": "delivered", "t3": "blocked"}

        summary = observe_session("Add authentication", tasks, outcomes)

        assert summary["type"] == "evolution"
        assert "Session:" in summary["trigger"]
        assert "2/3" in summary["resolution"]
        assert summary["_confidence"] == "high"

    def test_all_delivered(self):
        """Should handle all tasks delivered."""
        tasks = [
            {"id": "t1", "subject": "001: setup"},
            {"id": "t2", "subject": "002: implement"},
        ]
        outcomes = {"t1": "delivered", "t2": "delivered"}

        summary = observe_session("Add feature", tasks, outcomes)

        assert "2/2" in summary["resolution"]
        assert "Blocked: 0" not in summary["resolution"]


class TestShouldStore:
    """Tests for should_store function."""

    def test_high_meets_all_thresholds(self):
        """High confidence should meet all thresholds."""
        candidate = {"_confidence": "high"}
        assert should_store(candidate, "high") is True
        assert should_store(candidate, "medium") is True
        assert should_store(candidate, "low") is True

    def test_medium_meets_medium_and_low(self):
        """Medium confidence should meet medium and low thresholds."""
        candidate = {"_confidence": "medium"}
        assert should_store(candidate, "high") is False
        assert should_store(candidate, "medium") is True
        assert should_store(candidate, "low") is True

    def test_low_only_meets_low(self):
        """Low confidence should only meet low threshold."""
        candidate = {"_confidence": "low"}
        assert should_store(candidate, "high") is False
        assert should_store(candidate, "medium") is False
        assert should_store(candidate, "low") is True

    def test_missing_confidence_defaults_to_low(self):
        """Missing confidence should default to low."""
        candidate = {}
        assert should_store(candidate, "high") is False
        assert should_store(candidate, "medium") is False
        assert should_store(candidate, "low") is True


class TestStructuredLearning:
    """Tests for structured learning consumption from agents."""

    def test_observe_builder_structured_learning(self):
        """Builder's learned field should produce high-confidence candidates."""
        task = {
            "id": "task-001",
            "subject": "001: add-auth",
            "metadata": {
                "learned": [
                    {"type": "pattern", "trigger": "JWT validation in middleware", "resolution": "Use pyjwt with RS256"},
                    {"type": "failure", "trigger": "Missing pyjwt dependency", "resolution": "Add pyjwt to requirements.txt"}
                ]
            }
        }
        result = {"status": "delivered", "summary": "Added JWT auth"}
        files = ["src/auth/jwt.py"]

        candidates = observe_builder(task, result, files)

        # Should have structured learning entries with high confidence
        patterns = [c for c in candidates if c["type"] == "pattern"]
        failures = [c for c in candidates if c["type"] == "failure"]

        assert len(patterns) >= 1
        assert any("JWT validation" in p["trigger"] for p in patterns)
        assert any(p["_confidence"] == "high" for p in patterns)

        assert len(failures) >= 1
        assert any("pyjwt" in f["trigger"] for f in failures)

    def test_observe_builder_ignores_invalid_learned_types(self):
        """Invalid learned types should be ignored."""
        task = {
            "id": "task-001",
            "subject": "001: test",
            "metadata": {
                "learned": [
                    {"type": "invalid", "trigger": "test", "resolution": "test"},
                    {"type": "pattern", "trigger": "valid", "resolution": "valid"}
                ]
            }
        }
        result = {"status": "delivered", "summary": "Done"}

        candidates = observe_builder(task, result, [])

        # Only the valid pattern type should be extracted
        from_learned = [c for c in candidates if c["_confidence"] == "high"]
        assert len(from_learned) == 1
        assert from_learned[0]["type"] == "pattern"

    def test_observe_planner_structured_learned_block(self):
        """Planner's LEARNED: block should produce high-confidence decisions."""
        tasks = [{"subject": "001: setup", "description": "Setup auth", "metadata": {}}]
        planner_output = '''
PLAN_SPEC:
[{"seq": "001", "slug": "setup", "description": "Setup", "relevant_files": [], "blocked_by": []}]

PLAN_COMPLETE: 1 task

LEARNED: [
  {"type": "decision", "trigger": "chose JWT over sessions", "resolution": "stateless scaling requirement"}
]
'''
        candidates = observe_planner(tasks, {}, planner_output)

        # Should have high-confidence decision from LEARNED block
        decisions = [c for c in candidates if c["type"] == "decision" and c["_confidence"] == "high"]
        assert len(decisions) >= 1
        assert any("JWT over sessions" in d["trigger"] for d in decisions)

    def test_observe_planner_falls_back_to_regex(self):
        """Without LEARNED block, planner should use regex extraction."""
        tasks = [{
            "subject": "001: setup",
            "description": "Using FastAPI because it's async",
            "metadata": {}
        }]

        candidates = observe_planner(tasks, {}, None)

        # Should have medium-confidence decision from regex
        decisions = [c for c in candidates if c["type"] == "decision"]
        assert len(decisions) >= 1
        assert any(d["_confidence"] == "medium" for d in decisions)
