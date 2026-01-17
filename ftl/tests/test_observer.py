"""Test FTL observer.py operations."""

import json
from pathlib import Path


class TestListWorkspaces:
    """Test workspace listing."""

    def test_list_empty_dir(self, ftl_dir, lib_path):
        """Empty workspace dir returns empty lists."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        result = observer.list_workspaces(workspace_dir)

        assert result["complete"] == []
        assert result["blocked"] == []
        assert result["active"] == []

    def test_list_categorizes_by_status(self, ftl_dir, lib_path):
        """Workspaces categorized by filename suffix."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"

        # Create test files
        (workspace_dir / "001_test_complete.xml").write_text("<workspace/>")
        (workspace_dir / "002_test_blocked.xml").write_text("<workspace/>")
        (workspace_dir / "003_test_active.xml").write_text("<workspace/>")

        result = observer.list_workspaces(workspace_dir)

        assert len(result["complete"]) == 1
        assert len(result["blocked"]) == 1
        assert len(result["active"]) == 1


class TestScoring:
    """Test workspace scoring."""

    def test_score_basic_workspace(self, ftl_dir, lib_path, workspace_module):
        """Score a basic completed workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        # Create a minimal workspace
        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_test_complete.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-test" status="complete">
    <objective>Test objective</objective>
    <implementation>
        <delta>test.py</delta>
        <verify>pytest test.py</verify>
        <budget>5</budget>
    </implementation>
    <delivered>Implementation complete</delivered>
</workspace>""")

        result = observer.score_workspace(ws_path, {"failures": [], "patterns": []})

        assert "score" in result
        assert "breakdown" in result
        assert result["score"] >= 0

    def test_score_first_try_success(self, ftl_dir, lib_path):
        """First-try success gets +2 points."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_clean_complete.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-clean" status="complete">
    <objective>Clean implementation</objective>
    <implementation>
        <delta>clean.py</delta>
        <verify>pytest</verify>
        <budget>5</budget>
    </implementation>
    <delivered>Implemented successfully on first attempt</delivered>
</workspace>""")

        result = observer.score_workspace(ws_path, {"failures": [], "patterns": []})

        assert "first_try_success" in result["breakdown"]
        assert result["breakdown"]["first_try_success"] == 2

    def test_score_multi_file_delta(self, ftl_dir, lib_path):
        """Multi-file delta gets +1 point."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_multi_complete.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-multi" status="complete">
    <objective>Multi-file change</objective>
    <implementation>
        <delta>file1.py</delta>
        <delta>file2.py</delta>
        <verify>pytest</verify>
        <budget>5</budget>
    </implementation>
    <delivered>Updated multiple files</delivered>
</workspace>""")

        result = observer.score_workspace(ws_path, {"failures": [], "patterns": []})

        assert "multi_file" in result["breakdown"]
        assert result["breakdown"]["multi_file"] == 1


class TestFailureExtraction:
    """Test failure extraction from blocked workspaces."""

    def test_extract_failure_basic(self, ftl_dir, lib_path):
        """Extract failure from blocked workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_fail_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-fail" status="blocked">
    <objective>Failed task</objective>
    <implementation>
        <delta>broken.py</delta>
        <verify>pytest broken.py</verify>
        <budget>5</budget>
    </implementation>
    <delivered>BLOCKED: ImportError: No module named 'missing'
Tried: pip install missing
Unknown: Package not in PyPI</delivered>
</workspace>""")

        failure = observer.extract_failure(ws_path)

        assert "name" in failure
        assert "trigger" in failure
        assert "ImportError" in failure["trigger"]
        assert "cost" in failure
        assert failure["cost"] == 5000  # budget * 1000

    def test_extract_failure_with_fix_hint(self, ftl_dir, lib_path):
        """Extract fix hint from Tried section."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_hint_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-hint" status="blocked">
    <implementation>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: TypeError: expected str
Tried: cast to string using str()
Unknown: still failing</delivered>
</workspace>""")

        failure = observer.extract_failure(ws_path)

        assert "Attempted:" in failure["fix"]
        assert "cast to string" in failure["fix"]


class TestPatternExtraction:
    """Test pattern extraction from high-scoring workspaces."""

    def test_extract_pattern_basic(self, ftl_dir, lib_path):
        """Extract pattern from high-scoring workspace."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_good_complete.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-good" status="complete">
    <objective>Implement feature X</objective>
    <implementation>
        <delta>feature.py</delta>
        <delta>test_feature.py</delta>
        <verify>pytest</verify>
        <budget>5</budget>
    </implementation>
    <idioms framework="FastHTML">
        <required>Use @rt decorator</required>
    </idioms>
    <delivered>Implemented with proper idioms</delivered>
</workspace>""")

        score_data = observer.score_workspace(ws_path, {"failures": [], "patterns": []})
        pattern = observer.extract_pattern(ws_path, score_data)

        assert "name" in pattern
        assert "trigger" in pattern
        assert "insight" in pattern
        assert "saved" in pattern


class TestAnalyze:
    """Test full analysis workflow."""

    def test_analyze_empty(self, ftl_dir, lib_path):
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

    def test_analyze_extracts_from_blocked(self, ftl_dir, lib_path, memory_module):
        """Analyze extracts failures from blocked workspaces."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_err_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-err" status="blocked">
    <implementation>
        <delta>error.py</delta>
        <verify>python error.py</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: SyntaxError: invalid syntax at line 10</delivered>
</workspace>""")

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

    def test_verify_block_confirmed_when_command_fails(self, ftl_dir, lib_path):
        """Block is confirmed when verify command still fails."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_fail_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-fail" status="blocked">
    <implementation>
        <delta>broken.py</delta>
        <verify>exit 1</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: Tests still failing</delivered>
</workspace>""")

        result = observer.verify_block(ws_path, timeout=5)

        assert result["status"] == "CONFIRMED"
        assert "exit 1" in result["reason"]

    def test_verify_block_false_positive_when_passes(self, ftl_dir, lib_path):
        """Block is false positive when verify command now passes."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_maybe_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-maybe" status="blocked">
    <implementation>
        <delta>fixed.py</delta>
        <verify>exit 0</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: Was failing earlier</delivered>
</workspace>""")

        result = observer.verify_block(ws_path, timeout=5)

        assert result["status"] == "FALSE_POSITIVE"
        assert "pass" in result["reason"].lower()

    def test_verify_block_no_verify_command(self, ftl_dir, lib_path):
        """Block confirmed when no verify command exists."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_no_verify_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-noverify" status="blocked">
    <implementation>
        <delta>file.py</delta>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: No way to verify</delivered>
</workspace>""")

        result = observer.verify_block(ws_path, timeout=5)

        assert result["status"] == "CONFIRMED"
        assert "no verify" in result["reason"].lower()

    def test_verify_block_timeout_or_error_confirmed(self, ftl_dir, lib_path):
        """Block confirmed when verify command times out or fails to execute."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_timeout_blocked.xml"
        # Command that either times out or fails - either way confirms block
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-timeout" status="blocked">
    <implementation>
        <delta>slow.py</delta>
        <verify>/bin/sh -c "sleep 10"</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: Timeout or execution error</delivered>
</workspace>""")

        # Use very short timeout
        result = observer.verify_block(ws_path, timeout=1)

        # Block should be confirmed whether due to timeout or command failure
        assert result["status"] == "CONFIRMED"
        # Reason should indicate either timeout or non-zero exit
        assert "timeout" in result["reason"].lower() or "exit" in result["reason"].lower()

    def test_verify_block_error_in_output(self, ftl_dir, lib_path):
        """Block confirmed when output contains error keywords despite exit 0."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        ws_path = workspace_dir / "001_error_output_blocked.xml"
        # echo ERROR exits 0 but output has error keyword
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-errout" status="blocked">
    <implementation>
        <delta>errout.py</delta>
        <verify>echo "FAIL: something went wrong"</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: Output has error</delivered>
</workspace>""")

        result = observer.verify_block(ws_path, timeout=5)

        # Exit 0 but output contains FAIL -> still confirmed as blocked
        assert result["status"] == "CONFIRMED"

    def test_analyze_with_verification_enabled(self, ftl_dir, lib_path, memory_module):
        """Analyze with verify_blocks=True runs verification."""
        import sys
        sys.path.insert(0, str(lib_path))
        import observer

        workspace_dir = ftl_dir / ".ftl" / "workspace"
        # Create a blocked workspace with passing verify (false positive)
        ws_path = workspace_dir / "001_fp_blocked.xml"
        ws_path.write_text("""<?xml version='1.0' encoding='utf-8'?>
<workspace id="001-fp" status="blocked">
    <implementation>
        <delta>fp.py</delta>
        <verify>exit 0</verify>
        <budget>3</budget>
    </implementation>
    <delivered>BLOCKED: Was failing</delivered>
</workspace>""")

        # Analyze with verification enabled
        result = observer.analyze(workspace_dir, verify_blocks=True)

        assert result["workspaces"]["blocked"] == 1
        assert len(result["verified"]) == 1
        assert result["verified"][0]["status"] == "FALSE_POSITIVE"

        # False positive should NOT have failure extracted
        assert len(result["failures_extracted"]) == 0
