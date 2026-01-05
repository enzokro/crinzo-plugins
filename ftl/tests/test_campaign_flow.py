#!/usr/bin/env python3
"""Integration test for FTL campaign flow.

Validates each contract gate in the campaign lifecycle.
Run after contract fixes to verify enforcement.

Usage:
    python3 test_campaign_flow.py

Requires FTL_LIB environment variable or ~/.config/ftl/paths.sh
"""

import subprocess
import json
import os
import shutil
import tempfile
from pathlib import Path


def run_cmd(cmd, cwd=None):
    """Run shell command, return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout, result.stderr


def test_setup():
    """Create temp directory with FTL structure."""
    tmpdir = tempfile.mkdtemp(prefix="ftl_test_")
    os.makedirs(f"{tmpdir}/.ftl/campaigns/active", exist_ok=True)
    os.makedirs(f"{tmpdir}/.ftl/campaigns/complete", exist_ok=True)
    os.makedirs(f"{tmpdir}/.ftl/workspace", exist_ok=True)
    return tmpdir


def test_seq_normalization(lib_path, tmpdir):
    """Gate 1: Sequence numbers normalize to 3-digit."""
    # Add task with raw "1"
    # Note: -b flag must come before subcommand per argparse setup
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "test objective"'
    )
    assert code == 0, f"Campaign creation failed: {err}"

    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-task 1 test-slug'
    )
    assert code == 0, f"add-task failed: {err}"

    # Verify stored as "001"
    campaign_file = list(Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"))[0]
    campaign = json.loads(campaign_file.read_text())
    assert campaign["tasks"][0]["seq"] == "001", \
        f"Seq not normalized: {campaign['tasks'][0]['seq']}"

    print("  Gate 1: Sequence normalization")


def test_workspace_gate(lib_path, tmpdir):
    """Gate 2: update-task complete requires workspace file."""
    # Try to complete without workspace
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 001 complete'
    )
    assert code != 0, "Should fail without workspace file"
    assert "no workspace file" in err.lower(), f"Wrong error: {err}"

    # Create workspace file
    Path(f"{tmpdir}/.ftl/workspace/001_test-slug_complete.md").write_text("# Test")

    # Now should succeed
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 001 complete'
    )
    assert code == 0, f"Should succeed with workspace: {err}"

    print("  Gate 2: Workspace file required for completion")


def test_add_tasks_from_plan(lib_path, tmpdir):
    """Gate 3: Planner output parses correctly."""
    # Reset campaign
    for f in Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"):
        f.unlink()

    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "test2"')

    plan = """### Tasks

1. **first-task**: Do the first thing
   Delta: src/first.ts
   Depends: none
   Done when: first works
   Verify: npm test

2. **second-task**: Do the second thing
   Delta: src/second.ts
   Depends: first-task
   Done when: second works
   Verify: npm test
"""

    # Use heredoc-style to preserve newlines
    code, out, err = run_cmd(
        f'''python3 "{lib_path}/campaign.py" -b {tmpdir} add-tasks-from-plan << 'EOF'
{plan}
EOF''')
    assert code == 0, f"add-tasks-from-plan failed: {err}"
    assert "Added 2 tasks" in out, f"Expected 2 tasks: {out}"

    # Verify structure
    campaign_file = list(Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"))[0]
    campaign = json.loads(campaign_file.read_text())
    assert len(campaign["tasks"]) == 2
    assert campaign["tasks"][0]["seq"] == "001"
    assert campaign["tasks"][0]["slug"] == "first-task"
    assert campaign["tasks"][1]["seq"] == "002"

    print("  Gate 3: Planner output parsing")


def test_add_task_no_description(lib_path, tmpdir):
    """Gate 4: add-task rejects description argument."""
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-task 003 bad-task "with description"'
    )
    assert code != 0, "Should reject description argument"
    assert "unrecognized arguments" in err, f"Wrong error: {err}"

    print("  Gate 4: add-task rejects description")


def test_update_task_seq_normalization(lib_path, tmpdir):
    """Gate 5: update-task normalizes seq before gate check."""
    # Reset
    for f in Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"):
        f.unlink()
    for f in Path(f"{tmpdir}/.ftl/workspace").glob("*.md"):
        f.unlink()

    # Create campaign with task
    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "test3"')
    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-task 5 five-task')

    # Create workspace file with normalized name (005)
    Path(f"{tmpdir}/.ftl/workspace/005_five-task_complete.md").write_text("# Test")

    # Try to update with raw "5" - should work because CLI normalizes
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 5 complete'
    )
    assert code == 0, f"Should succeed with raw seq '5': {err}"
    assert "005" in out, f"Should show normalized seq: {out}"

    print("  Gate 5: update-task normalizes seq")


def test_update_task_mismatch_fix(lib_path, tmpdir):
    """Gate 6: update-task handles existing campaigns with non-normalized seq."""
    # Reset
    for f in Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"):
        f.unlink()
    for f in Path(f"{tmpdir}/.ftl/workspace").glob("*.md"):
        f.unlink()

    # Create campaign and manually inject task with non-normalized seq
    # This simulates a campaign created before the normalization fix
    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "test-mismatch"')

    # Manually modify campaign to have non-normalized seq (like old campaigns)
    campaign_file = list(Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"))[0]
    campaign = json.loads(campaign_file.read_text())
    campaign["tasks"] = [{"seq": "7", "slug": "legacy-task", "status": "pending"}]
    campaign_file.write_text(json.dumps(campaign, indent=2))

    # Create workspace file with normalized name
    Path(f"{tmpdir}/.ftl/workspace/007_legacy-task_complete.md").write_text("# Test")

    # Try to update - should match despite "7" vs "007"
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 7 complete'
    )
    assert code == 0, f"Should handle legacy seq format: {err}"

    # Verify campaign was updated AND seq was normalized
    campaign = json.loads(campaign_file.read_text())
    assert campaign["tasks"][0]["status"] == "complete", "Status not updated"
    assert campaign["tasks"][0]["seq"] == "007", f"Seq not normalized: {campaign['tasks'][0]['seq']}"

    print("  Gate 6: update-task handles legacy seq format")


def test_update_task_not_found(lib_path, tmpdir):
    """Gate 7: update-task fails if task not found."""
    # Reset
    for f in Path(f"{tmpdir}/.ftl/campaigns/active").glob("*.json"):
        f.unlink()

    # Create campaign with one task
    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} campaign "test-notfound"')
    run_cmd(f'python3 "{lib_path}/campaign.py" -b {tmpdir} add-task 1 only-task')

    # Try to update non-existent task with status "active" (not complete)
    # This bypasses the workspace gate and tests task lookup directly
    code, out, err = run_cmd(
        f'python3 "{lib_path}/campaign.py" -b {tmpdir} update-task 99 active'
    )
    assert code != 0, "Should fail for non-existent task"
    assert "not found" in err.lower(), f"Should report not found: {err}"

    print("  Gate 7: update-task fails for non-existent task")


def main():
    lib_path = os.environ.get("FTL_LIB")
    if not lib_path:
        # Try to source paths.sh
        code, out, _ = run_cmd("source ~/.config/ftl/paths.sh 2>/dev/null && echo $FTL_LIB")
        lib_path = out.strip()

    if not lib_path or not Path(lib_path).exists():
        print("ERROR: FTL_LIB not set or doesn't exist")
        print("Set FTL_LIB environment variable or ensure ~/.config/ftl/paths.sh exists")
        return 1

    print(f"Testing with FTL_LIB={lib_path}\n")

    tmpdir = test_setup()
    try:
        test_seq_normalization(lib_path, tmpdir)
        test_workspace_gate(lib_path, tmpdir)
        test_add_tasks_from_plan(lib_path, tmpdir)
        test_add_task_no_description(lib_path, tmpdir)
        test_update_task_seq_normalization(lib_path, tmpdir)
        test_update_task_mismatch_fix(lib_path, tmpdir)
        test_update_task_not_found(lib_path, tmpdir)
        print("\nAll gates passed")
        return 0
    except AssertionError as e:
        print(f"\nFAILED: {e}")
        return 1
    finally:
        shutil.rmtree(tmpdir)


if __name__ == "__main__":
    exit(main())
