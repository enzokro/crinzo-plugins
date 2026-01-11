#!/usr/bin/env python3
"""Test FTL workspace filename pattern contracts.

Validates workspace filenames match documentation:
  {NNN}_{slug}_{status}.xml
  {NNN}_{slug}_{status}_from-{NNN}.xml

Where:
  NNN = 3-digit zero-padded (001, 002, etc.)
  slug = kebab-case
  status = active | complete | blocked

Usage:
    python3 test_workspace_naming.py
    FTL_LIB=/path/to/lib python3 test_workspace_naming.py
"""

import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_lib_path():
    """Get FTL_LIB path from env or config."""
    lib_path = os.environ.get("FTL_LIB")
    if not lib_path:
        result = subprocess.run(
            "source ~/.config/ftl/paths.sh 2>/dev/null && echo $FTL_LIB",
            shell=True, capture_output=True, text=True
        )
        lib_path = result.stdout.strip()
    return lib_path


# Import parse_workspace_filename directly for unit testing
def import_parser(lib_path):
    """Import parse_workspace_filename from campaign.py."""
    sys.path.insert(0, lib_path)
    from campaign import parse_workspace_filename
    return parse_workspace_filename


# Canonical regex for workspace filenames (matches campaign.py implementation)
# Note: slug allows any characters (.+?) not just kebab-case
WORKSPACE_PATTERN = re.compile(
    r'^(\d{3})_(.+?)_(active|complete|blocked)(?:_from-(\d{3}))?\.xml$'
)


def validate_filename(filename):
    """Validate filename matches workspace pattern."""
    return WORKSPACE_PATTERN.match(filename) is not None


def glob_matches(pattern, filename):
    """Check if filename matches glob pattern."""
    return fnmatch.fnmatch(filename, pattern)


# --- Valid Pattern Tests ---

def test_valid_active(parse):
    """001_my-task_active.xml is valid."""
    filename = "001_my-task_active.xml"
    assert validate_filename(filename), f"Should be valid: {filename}"
    parsed = parse(filename)
    assert parsed is not None
    assert parsed["seq"] == "001"
    assert parsed["slug"] == "my-task"
    assert parsed["status"] == "active"
    print("  PASS: valid active")


def test_valid_complete(parse):
    """001_my-task_complete.xml is valid."""
    filename = "001_my-task_complete.xml"
    assert validate_filename(filename)
    parsed = parse(filename)
    assert parsed["status"] == "complete"
    print("  PASS: valid complete")


def test_valid_blocked(parse):
    """001_my-task_blocked.xml is valid."""
    filename = "001_my-task_blocked.xml"
    assert validate_filename(filename)
    parsed = parse(filename)
    assert parsed["status"] == "blocked"
    print("  PASS: valid blocked")


def test_valid_lineage(parse):
    """002_child_active_from-001.xml is valid."""
    filename = "002_child-task_active_from-001.xml"
    assert validate_filename(filename)
    parsed = parse(filename)
    assert parsed["seq"] == "002"
    assert parsed["slug"] == "child-task"
    assert parsed["status"] == "active"
    assert parsed["parent"] == "001"
    print("  PASS: valid lineage")


def test_valid_complex_slug(parse):
    """Slug with multiple hyphens is valid."""
    filename = "005_my-complex-task-name_active.xml"
    assert validate_filename(filename)
    parsed = parse(filename)
    assert parsed["slug"] == "my-complex-task-name"
    print("  PASS: valid complex slug")


def test_valid_numbers_in_slug(parse):
    """Slug with numbers is valid."""
    filename = "001_task-v2-beta3_active.xml"
    assert validate_filename(filename)
    parsed = parse(filename)
    assert parsed["slug"] == "task-v2-beta3"
    print("  PASS: valid numbers in slug")


# --- Invalid Pattern Tests ---

def test_invalid_seq_1digit(parse):
    """1_task_active.xml is invalid (1-digit seq)."""
    filename = "1_task_active.xml"
    assert not validate_filename(filename), f"Should be invalid: {filename}"
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid 1-digit seq")


def test_invalid_seq_2digit(parse):
    """01_task_active.xml is invalid (2-digit seq)."""
    filename = "01_task_active.xml"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid 2-digit seq")


def test_invalid_seq_4digit(parse):
    """0001_task_active.xml is invalid (4-digit seq)."""
    filename = "0001_task_active.xml"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid 4-digit seq")


def test_invalid_status(parse):
    """001_task_pending.xml is invalid (wrong status)."""
    filename = "001_task_pending.xml"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid status")


def test_invalid_no_slug(parse):
    """001__active.xml is invalid (empty slug)."""
    filename = "001__active.xml"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid empty slug")


def test_uppercase_slug_allowed(parse):
    """001_MyTask_active.xml is valid (implementation allows uppercase)."""
    filename = "001_MyTask_active.xml"
    # Note: Implementation uses (.+?) which allows uppercase
    # This is more permissive than kebab-case convention
    parsed = parse(filename)
    assert parsed is not None
    assert parsed["slug"] == "MyTask"
    print("  PASS: uppercase slug allowed")


def test_underscore_slug_allowed(parse):
    """001_my_task_active.xml is valid (implementation parses correctly)."""
    filename = "001_my_task_active.xml"
    # Note: Regex uses (.+?)_ which matches minimally then backtracks
    # to find valid status. Result: slug=my_task, status=active
    parsed = parse(filename)
    assert parsed is not None
    assert parsed["slug"] == "my_task"
    assert parsed["status"] == "active"
    print("  PASS: underscore slug allowed")


def test_invalid_missing_extension(parse):
    """001_task_active (no .xml) is invalid."""
    filename = "001_task_active"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid missing extension")


def test_invalid_wrong_extension(parse):
    """001_task_active.txt is invalid."""
    filename = "001_task_active.txt"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid wrong extension")


def test_invalid_lineage_format(parse):
    """002_task_active_from001.xml is invalid (missing hyphen)."""
    filename = "002_task_active_from001.xml"
    assert not validate_filename(filename)
    parsed = parse(filename)
    assert parsed is None
    print("  PASS: invalid lineage format")


# --- Glob Pattern Tests (for update-task gate) ---

def test_workspace_gate_glob_matches_complete():
    """update-task gate glob matches complete files."""
    pattern = "001_*_complete*.xml"
    assert glob_matches(pattern, "001_my-task_complete.xml")
    assert glob_matches(pattern, "001_another-task_complete.xml")
    assert glob_matches(pattern, "001_task_complete_extra.xml")
    print("  PASS: gate glob matches complete")


def test_workspace_gate_glob_rejects_active():
    """update-task gate glob rejects active files."""
    pattern = "001_*_complete*.xml"
    assert not glob_matches(pattern, "001_task_active.xml")
    assert not glob_matches(pattern, "001_task_blocked.xml")
    print("  PASS: gate glob rejects active")


def test_workspace_gate_glob_rejects_wrong_seq():
    """update-task gate glob rejects wrong sequence."""
    pattern = "001_*_complete*.xml"
    assert not glob_matches(pattern, "002_task_complete.xml")
    assert not glob_matches(pattern, "010_task_complete.xml")
    print("  PASS: gate glob rejects wrong seq")


def test_workspace_gate_glob_normalized():
    """Gate uses normalized 3-digit seq in glob."""
    # The gate should use f"{seq}_*_complete*.xml" with normalized seq
    seq = "5"
    normalized = f"{int(seq):03d}"
    pattern = f"{normalized}_*_complete*.xml"
    assert pattern == "005_*_complete*.xml"
    assert glob_matches(pattern, "005_five-task_complete.xml")
    assert not glob_matches(pattern, "5_five-task_complete.xml")
    print("  PASS: gate uses normalized seq")


# --- Integration Test ---

def test_gate_integration(lib_path):
    """update-task complete uses correct glob pattern."""
    tmpdir = tempfile.mkdtemp(prefix="ftl_workspace_test_")
    try:
        # Create FTL structure
        os.makedirs(f"{tmpdir}/.ftl/campaigns/active", exist_ok=True)
        os.makedirs(f"{tmpdir}/.ftl/workspace", exist_ok=True)

        # Create campaign with task
        subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "gate test"',
            shell=True, capture_output=True
        )
        subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-task 1 test-task',
            shell=True, capture_output=True
        )

        # Without workspace file - should fail
        result = subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 001 complete',
            shell=True, capture_output=True, text=True
        )
        assert result.returncode != 0, "Should fail without workspace"
        assert "no workspace file" in result.stderr.lower()

        # With wrong filename format - should fail
        Path(f"{tmpdir}/.ftl/workspace/1_test-task_complete.xml").write_text("# Wrong format")
        result = subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 001 complete',
            shell=True, capture_output=True, text=True
        )
        assert result.returncode != 0, "Should fail with wrong format"

        # Remove wrong file, create correct one
        Path(f"{tmpdir}/.ftl/workspace/1_test-task_complete.xml").unlink()
        Path(f"{tmpdir}/.ftl/workspace/001_test-task_complete.xml").write_text("# Correct format")

        result = subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 001 complete',
            shell=True, capture_output=True, text=True
        )
        assert result.returncode == 0, f"Should succeed with correct format: {result.stderr}"

        print("  PASS: gate integration")

    finally:
        shutil.rmtree(tmpdir)


def main():
    lib_path = get_lib_path()
    if not lib_path or not Path(lib_path).exists():
        print("ERROR: FTL_LIB not set or doesn't exist")
        print("Set FTL_LIB environment variable or ensure ~/.config/ftl/paths.sh exists")
        return 1

    print(f"Testing workspace naming with FTL_LIB={lib_path}\n")

    # Import parser
    parse = import_parser(lib_path)

    # Pattern validation tests
    pattern_tests = [
        test_valid_active,
        test_valid_complete,
        test_valid_blocked,
        test_valid_lineage,
        test_valid_complex_slug,
        test_valid_numbers_in_slug,
        test_invalid_seq_1digit,
        test_invalid_seq_2digit,
        test_invalid_seq_4digit,
        test_invalid_status,
        test_invalid_no_slug,
        test_uppercase_slug_allowed,
        test_underscore_slug_allowed,
        test_invalid_missing_extension,
        test_invalid_wrong_extension,
        test_invalid_lineage_format,
    ]

    # Glob tests (no parser needed)
    glob_tests = [
        test_workspace_gate_glob_matches_complete,
        test_workspace_gate_glob_rejects_active,
        test_workspace_gate_glob_rejects_wrong_seq,
        test_workspace_gate_glob_normalized,
    ]

    passed = 0
    failed = 0

    for test in pattern_tests:
        try:
            test(parse)
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1

    for test in glob_tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1

    # Integration test
    try:
        test_gate_integration(lib_path)
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_gate_integration: {e}")
        failed += 1
    except Exception as e:
        print(f"  ERROR: test_gate_integration: {e}")
        failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
