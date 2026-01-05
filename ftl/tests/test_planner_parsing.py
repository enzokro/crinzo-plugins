#!/usr/bin/env python3
"""Test FTL planner output parsing contracts.

Validates add-tasks-from-plan parses exactly the documented format.
Run after parser changes to verify contract compliance.

Usage:
    python3 test_planner_parsing.py
    FTL_LIB=/path/to/lib python3 test_planner_parsing.py
"""

import subprocess
import json
import os
import shutil
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


# Import parse_planner_output directly for unit testing
def import_parser(lib_path):
    """Import parse_planner_output from campaign.py."""
    sys.path.insert(0, lib_path)
    from campaign import parse_planner_output
    return parse_planner_output


# --- Valid Format Tests ---

VALID_PLAN = """## Campaign: Test Campaign

### Confidence: PROCEED

Rationale: Clear requirements.

### Tasks

1. **first-task**: Do the first thing
   Delta: src/first.ts
   Depends: none
   Done when: first works
   Verify: npm test

2. **second-task**: Do the second thing
   Delta: src/second.ts
   Depends: first-task
   Done when: second works
   Verify: npm run build

### Memory Applied

- #pattern/test from 001: applied pattern
"""


def test_parses_valid_format(parse):
    """Valid markdown: 2 tasks extracted."""
    tasks = parse(VALID_PLAN)
    assert len(tasks) == 2, f"Expected 2 tasks, got {len(tasks)}"
    print("  PASS: parses valid format")


def test_extracts_slug(parse):
    """**my-slug**: extracts slug correctly."""
    tasks = parse(VALID_PLAN)
    assert tasks[0]["slug"] == "first-task"
    assert tasks[1]["slug"] == "second-task"
    print("  PASS: extracts slug")


def test_extracts_delta(parse):
    """Delta: src/a.ts extracts delta correctly."""
    tasks = parse(VALID_PLAN)
    assert tasks[0]["delta"] == "src/first.ts"
    assert tasks[1]["delta"] == "src/second.ts"
    print("  PASS: extracts delta")


def test_extracts_depends(parse):
    """Depends: prev-task extracts depends correctly."""
    tasks = parse(VALID_PLAN)
    assert tasks[0]["depends"] == "none"
    assert tasks[1]["depends"] == "first-task"
    print("  PASS: extracts depends")


def test_extracts_verify(parse):
    """Verify: cmd extracts verify correctly."""
    tasks = parse(VALID_PLAN)
    assert tasks[0]["verify"] == "npm test"
    assert tasks[1]["verify"] == "npm run build"
    print("  PASS: extracts verify")


def test_extracts_description(parse):
    """Description text after slug is captured."""
    tasks = parse(VALID_PLAN)
    assert "first thing" in tasks[0]["description"]
    assert "second thing" in tasks[1]["description"]
    print("  PASS: extracts description")


def test_ignores_other_sections(parse):
    """Content before/after ### Tasks is ignored."""
    plan_with_extras = """# Header

Some preamble text.

### Tasks

1. **only-task**: The only task
   Delta: src/only.ts
   Depends: none
   Done when: done
   Verify: test

### Memory Applied

- #pattern/extra: should be ignored

## Footer

More content.
"""
    tasks = parse(plan_with_extras)
    assert len(tasks) == 1
    assert tasks[0]["slug"] == "only-task"
    print("  PASS: ignores other sections")


def test_handles_minimal_task(parse):
    """Task with only required fields parses."""
    minimal = """### Tasks

1. **minimal-task**: Just description
"""
    tasks = parse(minimal)
    assert len(tasks) == 1
    assert tasks[0]["slug"] == "minimal-task"
    assert tasks[0]["delta"] == ""  # Empty, not missing
    print("  PASS: handles minimal task")


def test_handles_multiline_content(parse):
    """Multiple property lines per task."""
    plan = """### Tasks

1. **complex-task**: Complex description with details
   Delta: src/a.ts, src/b.ts
   Depends: none
   Done when: everything works correctly
   Verify: npm test && npm run lint
"""
    tasks = parse(plan)
    assert len(tasks) == 1
    assert "a.ts" in tasks[0]["delta"]
    print("  PASS: handles multiline content")


# --- Invalid Format Tests ---

def test_rejects_no_tasks_section(parse):
    """Empty input with no ### Tasks raises error."""
    empty = """## Campaign

Some content but no Tasks section.
"""
    tasks = parse(empty)
    assert len(tasks) == 0, "Should return empty list for no tasks"
    print("  PASS: rejects no tasks section")


def test_ignores_wrong_heading_level(parse):
    """## Tasks (wrong level) is ignored."""
    wrong_level = """## Tasks

1. **wrong-task**: Should not parse

### Tasks

1. **right-task**: Should parse
   Delta: src/right.ts
"""
    tasks = parse(wrong_level)
    # Should only get right-task (after ### Tasks)
    assert len(tasks) == 1
    assert tasks[0]["slug"] == "right-task"
    print("  PASS: ignores wrong heading level")


def test_ignores_missing_bold_markers(parse):
    """1. task-name: (no **) is ignored."""
    no_bold = """### Tasks

1. plain-task: No bold markers
   Delta: src/plain.ts

2. **bold-task**: Has bold markers
   Delta: src/bold.ts
"""
    tasks = parse(no_bold)
    # Should only get bold-task
    assert len(tasks) == 1
    assert tasks[0]["slug"] == "bold-task"
    print("  PASS: ignores missing bold markers")


def test_case_sensitive_properties(parse):
    """Property names are case-sensitive (Delta not DELTA)."""
    wrong_case = """### Tasks

1. **case-task**: Test case sensitivity
   DELTA: src/wrong.ts
   delta: src/also-wrong.ts
   Delta: src/correct.ts
"""
    tasks = parse(wrong_case)
    assert len(tasks) == 1
    # Only correct Delta: should be captured
    assert tasks[0]["delta"] == "src/correct.ts"
    print("  PASS: case-sensitive properties")


def test_handles_empty_tasks_section(parse):
    """### Tasks with no tasks returns empty."""
    empty_section = """### Tasks

### Next Section
"""
    tasks = parse(empty_section)
    assert len(tasks) == 0
    print("  PASS: handles empty tasks section")


def test_handles_unicode(parse):
    """Unicode in descriptions is preserved."""
    unicode_plan = """### Tasks

1. **unicode-task**: Task with emoji and unicode
   Delta: src/file.ts
"""
    tasks = parse(unicode_plan)
    assert len(tasks) == 1
    assert "emoji" in tasks[0]["description"] or "unicode" in tasks[0]["description"]
    print("  PASS: handles unicode")


# --- Integration Test via CLI ---

def test_cli_integration(lib_path):
    """add-tasks-from-plan CLI parses correctly."""
    tmpdir = tempfile.mkdtemp(prefix="ftl_planner_test_")
    try:
        # Create FTL structure
        os.makedirs(f"{tmpdir}/.ftl/campaigns/active", exist_ok=True)
        os.makedirs(f"{tmpdir}/workspace", exist_ok=True)

        # Create campaign
        subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "cli test"',
            shell=True, capture_output=True
        )

        # Add tasks from plan
        result = subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-tasks-from-plan',
            shell=True, capture_output=True, text=True, input=VALID_PLAN
        )

        assert result.returncode == 0, f"CLI failed: {result.stderr}"
        assert "Added 2 tasks" in result.stdout

        # Verify via active command
        result = subprocess.run(
            f'python3 "{lib_path}/campaign.py" -b {tmpdir} active',
            shell=True, capture_output=True, text=True
        )
        campaign = json.loads(result.stdout)
        assert len(campaign["tasks"]) == 2
        assert campaign["tasks"][0]["seq"] == "001"
        assert campaign["tasks"][1]["seq"] == "002"

        print("  PASS: CLI integration")

    finally:
        shutil.rmtree(tmpdir)


def main():
    lib_path = get_lib_path()
    if not lib_path or not Path(lib_path).exists():
        print("ERROR: FTL_LIB not set or doesn't exist")
        print("Set FTL_LIB environment variable or ensure ~/.config/ftl/paths.sh exists")
        return 1

    print(f"Testing planner parsing with FTL_LIB={lib_path}\n")

    # Import parser
    parse = import_parser(lib_path)

    # Unit tests
    unit_tests = [
        test_parses_valid_format,
        test_extracts_slug,
        test_extracts_delta,
        test_extracts_depends,
        test_extracts_verify,
        test_extracts_description,
        test_ignores_other_sections,
        test_handles_minimal_task,
        test_handles_multiline_content,
        test_rejects_no_tasks_section,
        test_ignores_wrong_heading_level,
        test_ignores_missing_bold_markers,
        test_case_sensitive_properties,
        test_handles_empty_tasks_section,
        test_handles_unicode,
    ]

    passed = 0
    failed = 0

    for test in unit_tests:
        try:
            test(parse)
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1

    # CLI integration test
    try:
        test_cli_integration(lib_path)
        passed += 1
    except AssertionError as e:
        print(f"  FAIL: test_cli_integration: {e}")
        failed += 1
    except Exception as e:
        print(f"  ERROR: test_cli_integration: {e}")
        failed += 1

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
