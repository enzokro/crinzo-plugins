"""Test FTL observer.py operations."""

import json
from pathlib import Path


class TestListWorkspaces:
    """Test workspace listing."""

    def test_list_empty_dir(self, ftl_dir, lib_path, test_db):
        """Empty workspace dir returns empty lists."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        result = observer.list_workspaces(workspace_dir)

        assert result["complete"] == []
        assert result["blocked"] == []
        assert result["active"] == []

    def test_list_categorizes_by_status(self, ftl_dir, lib_path, create_workspace):
        """Workspaces categorized by status."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Create test workspaces in database
        create_workspace("001-test", status="complete", delivered="Done")
        create_workspace("002-test", status="blocked", delivered="BLOCKED: Failed")
        create_workspace("003-test", status="active")

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        result = observer.list_workspaces(workspace_dir)

        assert len(result["complete"]) == 1
        assert len(result["blocked"]) == 1
        assert len(result["active"]) == 1


class TestScoring:
    """Test workspace scoring."""

    def test_score_basic_workspace(self, ftl_dir, lib_path, create_workspace):
        """Score a basic completed workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Create workspace in database
        create_workspace(
            "001-test",
            status="complete",
            objective="Test objective",
            delta=["test.py"],
            verify="pytest test.py",
            budget=5,
            delivered="Implementation complete"
        )

        # Get the workspace from database for scoring
        ws_data = {
            "id": "001-test",
            "workspace_id": "001-test",
            "status": "complete",
            "objective": "Test objective",
            "delta": ["test.py"],
            "verify": "pytest test.py",
            "budget": 5,
            "delivered": "Implementation complete"
        }

        result = observer.score_workspace(ws_data, {"failures": [], "patterns": []})

        assert "score" in result
        assert "breakdown" in result
        assert result["score"] >= 0

    def test_score_first_try_success(self, ftl_dir, lib_path, create_workspace):
        """First-try success gets +2 points."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-clean",
            "workspace_id": "001-clean",
            "status": "complete",
            "objective": "Clean implementation",
            "delta": ["clean.py"],
            "verify": "pytest",
            "budget": 5,
            "delivered": "Implemented successfully on first attempt"
        }

        result = observer.score_workspace(ws_data, {"failures": [], "patterns": []})

        assert "first_try_success" in result["breakdown"]
        assert result["breakdown"]["first_try_success"] == 2

    def test_score_multi_file_delta(self, ftl_dir, lib_path, create_workspace):
        """Multi-file delta gets +1 point."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-multi",
            "workspace_id": "001-multi",
            "status": "complete",
            "objective": "Multi-file change",
            "delta": ["file1.py", "file2.py"],
            "verify": "pytest",
            "budget": 5,
            "delivered": "Updated multiple files"
        }

        result = observer.score_workspace(ws_data, {"failures": [], "patterns": []})

        assert "multi_file" in result["breakdown"]
        assert result["breakdown"]["multi_file"] == 1


class TestFailureExtraction:
    """Test failure extraction from blocked workspaces."""

    def test_extract_failure_basic(self, ftl_dir, lib_path, create_workspace):
        """Extract failure from blocked workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-fail",
            "workspace_id": "001-fail",
            "status": "blocked",
            "objective": "Failed task",
            "delta": ["broken.py"],
            "verify": "pytest broken.py",
            "budget": 5,
            "delivered": "BLOCKED: ImportError: No module named 'missing'\nTried: pip install missing\nUnknown: Package not in PyPI"
        }

        failure = observer.extract_failure(ws_data)

        assert "name" in failure
        assert "trigger" in failure
        assert "ImportError" in failure["trigger"]
        assert "cost" in failure
        assert failure["cost"] == 5000  # budget * 1000

    def test_extract_failure_with_fix_hint(self, ftl_dir, lib_path, create_workspace):
        """Extract fix hint from Tried section."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-hint",
            "workspace_id": "001-hint",
            "status": "blocked",
            "objective": "Hint test",
            "delta": ["file.py"],
            "verify": "pytest",
            "budget": 3,
            "delivered": "BLOCKED: TypeError: expected str\nTried: cast to string using str()\nUnknown: still failing"
        }

        failure = observer.extract_failure(ws_data)

        assert "Attempted:" in failure["fix"]
        assert "cast to string" in failure["fix"]


class TestPatternExtraction:
    """Test pattern extraction from high-scoring workspaces."""

    def test_extract_pattern_basic(self, ftl_dir, lib_path, create_workspace):
        """Extract pattern from high-scoring workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-good",
            "workspace_id": "001-good",
            "status": "complete",
            "objective": "Implement feature X",
            "delta": ["feature.py", "test_feature.py"],
            "verify": "pytest",
            "budget": 5,
            "delivered": "Implemented with proper idioms",
            "framework": "FastHTML",
            "idioms": {"required": ["Use @rt decorator"], "forbidden": []}
        }

        score_data = observer.score_workspace(ws_data, {"failures": [], "patterns": []})
        pattern = observer.extract_pattern(ws_data, score_data)

        assert "name" in pattern
        assert "trigger" in pattern
        assert "insight" in pattern
        assert "saved" in pattern


class TestAnalyze:
    """Test full analysis workflow."""

    def test_analyze_empty(self, ftl_dir, lib_path, test_db):
        """Analyze empty workspace directory."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        result = observer.analyze(workspace_dir, verify_blocks=False)

        assert result["workspaces"]["complete"] == 0
        assert result["workspaces"]["blocked"] == 0
        assert result["failures_extracted"] == []
        assert result["patterns_extracted"] == []

    def test_analyze_extracts_from_blocked(self, ftl_dir, lib_path, create_workspace, memory_module):
        """Analyze extracts failures from blocked workspaces."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Create blocked workspace in database
        create_workspace(
            "001-err",
            status="blocked",
            delta=["error.py"],
            verify="python error.py",
            budget=3,
            delivered="BLOCKED: SyntaxError: invalid syntax at line 10"
        )

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        result = observer.analyze(workspace_dir, verify_blocks=False)

        assert result["workspaces"]["blocked"] == 1
        assert len(result["failures_extracted"]) == 1
        # Accept: name contains "SyntaxError", result is "added", or result starts with "merged:"
        extracted = result["failures_extracted"][0]
        assert (
            "syntaxerror" in extracted["name"].lower() or
            extracted["result"] == "added" or
            extracted["result"].startswith("merged:")
        )


class TestHelpers:
    """Test helper functions."""

    def test_slugify(self, lib_path):
        """Slugify converts text to kebab-case."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        assert observer._slugify("Hello World") == "hello-world"
        assert observer._slugify("ImportError: No module") == "importerror-no-module"
        assert observer._slugify("Test@#$String!!!") == "teststring"

    def test_generalize_to_regex(self, lib_path):
        """Generalize trigger to regex pattern."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Numbers become \d+
        pattern = observer._generalize_to_regex("Error at line 42")
        assert "\\d+" in pattern


class TestBlockVerification:
    """Test verify_block functionality."""

    def test_verify_block_confirmed_when_command_fails(self, ftl_dir, lib_path, create_workspace):
        """Block is confirmed when verify command still fails."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-fail",
            "workspace_id": "001-fail",
            "status": "blocked",
            "delta": ["broken.py"],
            "verify": "exit 1",
            "budget": 3,
            "delivered": "BLOCKED: Tests still failing"
        }

        result = observer.verify_block(ws_data, timeout=5)

        assert result["status"] == "CONFIRMED"
        assert "exit 1" in result["reason"]

    def test_verify_block_false_positive_when_passes(self, ftl_dir, lib_path, create_workspace):
        """Block is false positive when verify command now passes."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-maybe",
            "workspace_id": "001-maybe",
            "status": "blocked",
            "delta": ["fixed.py"],
            "verify": "exit 0",
            "budget": 3,
            "delivered": "BLOCKED: Was failing earlier"
        }

        result = observer.verify_block(ws_data, timeout=5)

        assert result["status"] == "FALSE_POSITIVE"
        assert "pass" in result["reason"].lower()

    def test_verify_block_no_verify_command(self, ftl_dir, lib_path, create_workspace):
        """Block confirmed when no verify command exists."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-noverify",
            "workspace_id": "001-noverify",
            "status": "blocked",
            "delta": ["file.py"],
            "verify": "",
            "budget": 3,
            "delivered": "BLOCKED: No way to verify"
        }

        result = observer.verify_block(ws_data, timeout=5)

        assert result["status"] == "CONFIRMED"
        assert "no verify" in result["reason"].lower()

    def test_verify_block_timeout_or_error_confirmed(self, ftl_dir, lib_path, create_workspace):
        """Block confirmed when verify command times out or fails to execute."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-timeout",
            "workspace_id": "001-timeout",
            "status": "blocked",
            "delta": ["slow.py"],
            "verify": "/bin/sh -c 'sleep 10'",
            "budget": 3,
            "delivered": "BLOCKED: Timeout or execution error"
        }

        # Use very short timeout
        result = observer.verify_block(ws_data, timeout=1)

        # Block should be confirmed whether due to timeout or command failure
        assert result["status"] == "CONFIRMED"
        # Reason should indicate either timeout or non-zero exit
        assert "timeout" in result["reason"].lower() or "exit" in result["reason"].lower()

    def test_verify_block_error_in_output(self, ftl_dir, lib_path, create_workspace):
        """Block confirmed when output contains error keywords despite exit 0."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        ws_data = {
            "id": "001-errout",
            "workspace_id": "001-errout",
            "status": "blocked",
            "delta": ["errout.py"],
            "verify": "echo 'FAIL: something went wrong'",
            "budget": 3,
            "delivered": "BLOCKED: Output has error"
        }

        result = observer.verify_block(ws_data, timeout=5)

        # Exit 0 but output contains FAIL -> still confirmed as blocked
        assert result["status"] == "CONFIRMED"

    def test_analyze_with_verification_enabled(self, ftl_dir, lib_path, create_workspace, memory_module):
        """Analyze with verify_blocks=True runs verification."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Create a blocked workspace with passing verify (false positive)
        create_workspace(
            "001-fp",
            status="blocked",
            delta=["fp.py"],
            verify="exit 0",
            budget=3,
            delivered="BLOCKED: Was failing"
        )

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        # Analyze with verification enabled
        result = observer.analyze(workspace_dir, verify_blocks=True)

        assert result["workspaces"]["blocked"] == 1
        assert len(result["verified"]) == 1
        assert result["verified"][0]["status"] == "FALSE_POSITIVE"

        # False positive should NOT have failure extracted
        assert len(result["failures_extracted"]) == 0
