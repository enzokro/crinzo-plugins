#!/usr/bin/env python3
"""Test FTL campaign.py CLI contracts.

Validates every subcommand matches documentation exactly.
Run after CLI changes to verify contract compliance.

Usage:
    python3 test_cli_contracts.py
    FTL_LIB=/path/to/lib python3 test_cli_contracts.py
"""

import subprocess
import json
import os
import shutil
import tempfile
from pathlib import Path


# Required fields for valid campaign schema
REQUIRED_CAMPAIGN_FIELDS = [
    "id", "objective", "started", "session", "status", "tasks",
    "precedent_used", "patterns_emerged", "signals_given",
    "revisions", "critic_verdicts"
]


def get_lib_path():
    """Get FTL_LIB path from env or config."""
    lib_path = os.environ.get("FTL_LIB")
    if not lib_path:
        code, out, _ = subprocess.run(
            "source ~/.config/ftl/paths.sh 2>/dev/null && echo $FTL_LIB",
            shell=True, capture_output=True, text=True
        ).returncode, subprocess.run(
            "source ~/.config/ftl/paths.sh 2>/dev/null && echo $FTL_LIB",
            shell=True, capture_output=True, text=True
        ).stdout, None
        lib_path = out.strip()
    return lib_path


def run_cmd(cmd, cwd=None, stdin=None):
    """Run shell command, return (exit_code, stdout, stderr)."""
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True,
        cwd=cwd, input=stdin
    )
    return result.returncode, result.stdout, result.stderr


class TestFixture:
    """Test fixture with temp directory and FTL structure."""

    def __init__(self, lib_path):
        self.lib_path = lib_path
        self.tmpdir = None

    def setup(self):
        """Create temp directory with FTL structure."""
        self.tmpdir = tempfile.mkdtemp(prefix="ftl_cli_test_")
        os.makedirs(f"{self.tmpdir}/.ftl/campaigns/active", exist_ok=True)
        os.makedirs(f"{self.tmpdir}/.ftl/campaigns/complete", exist_ok=True)
        os.makedirs(f"{self.tmpdir}/workspace", exist_ok=True)
        return self.tmpdir

    def teardown(self):
        """Clean up temp directory."""
        if self.tmpdir:
            shutil.rmtree(self.tmpdir)

    def cmd(self, subcmd, stdin=None):
        """Run campaign.py subcommand."""
        return run_cmd(
            f'python3 "{self.lib_path}/campaign.py" -b {self.tmpdir} {subcmd}',
            stdin=stdin
        )


# --- CLI Contract Tests ---

def test_campaign_create(fixture):
    """campaign <obj>: Creates JSON with all required fields."""
    code, out, err = fixture.cmd('campaign "test objective"')
    assert code == 0, f"Command failed: {err}"

    campaign = json.loads(out)
    missing = [f for f in REQUIRED_CAMPAIGN_FIELDS if f not in campaign]
    assert not missing, f"Missing required fields: {missing}"

    # Validate specific field values
    assert campaign["objective"] == "test objective"
    assert campaign["status"] == "active"
    assert campaign["tasks"] == []
    assert campaign["revisions"] == 0

    print("  PASS: campaign create")


def test_campaign_no_arg(fixture):
    """campaign (no arg): Returns active or 'No active campaign'."""
    # Without active campaign
    code, out, err = fixture.cmd('campaign')
    assert code == 0
    assert "No active campaign" in out

    # Create campaign, then query
    fixture.cmd('campaign "test"')
    code, out, err = fixture.cmd('campaign')
    assert code == 0
    campaign = json.loads(out)
    assert campaign["objective"] == "test"

    print("  PASS: campaign no-arg")


def test_active(fixture):
    """active: Returns JSON or 'No active campaign'."""
    # Without active
    code, out, err = fixture.cmd('active')
    assert code == 0
    assert "No active campaign" in out

    # With active
    fixture.cmd('campaign "active test"')
    code, out, err = fixture.cmd('active')
    assert code == 0
    campaign = json.loads(out)
    assert "id" in campaign

    print("  PASS: active")


def test_status(fixture):
    """status: Returns formatted output."""
    # Without campaign
    code, out, err = fixture.cmd('status')
    assert code == 0
    assert "No active campaign" in out

    # With campaign and task
    fixture.cmd('campaign "status test"')
    fixture.cmd('add-task 1 my-task')
    code, out, err = fixture.cmd('status')
    assert code == 0
    assert "Campaign:" in out
    assert "001_my-task" in out

    print("  PASS: status")


def test_add_task_two_args(fixture):
    """add-task <seq> <slug>: Accepts exactly 2 positional args."""
    fixture.cmd('campaign "add-task test"')

    code, out, err = fixture.cmd('add-task 1 my-task')
    assert code == 0, f"add-task failed: {err}"
    assert "Added task" in out

    # Verify stored correctly
    code, out, _ = fixture.cmd('active')
    campaign = json.loads(out)
    assert len(campaign["tasks"]) == 1
    assert campaign["tasks"][0]["slug"] == "my-task"
    assert campaign["tasks"][0]["seq"] == "001"  # Normalized

    print("  PASS: add-task two args")


def test_add_task_rejects_three(fixture):
    """add-task rejects 3rd positional argument (description)."""
    fixture.cmd('campaign "reject test"')

    code, out, err = fixture.cmd('add-task 1 bad-task "with description"')
    assert code != 0, "Should reject 3rd argument"
    assert "unrecognized arguments" in err

    print("  PASS: add-task rejects description")


def test_add_tasks_from_plan(fixture):
    """add-tasks-from-plan: Parses stdin markdown."""
    fixture.cmd('campaign "plan test"')

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

    code, out, err = fixture.cmd('add-tasks-from-plan', stdin=plan)
    assert code == 0, f"add-tasks-from-plan failed: {err}"
    assert "Added 2 tasks" in out

    # Verify tasks stored correctly
    code, out, _ = fixture.cmd('active')
    campaign = json.loads(out)
    assert len(campaign["tasks"]) == 2
    assert campaign["tasks"][0]["seq"] == "001"
    assert campaign["tasks"][0]["slug"] == "first-task"
    assert campaign["tasks"][1]["seq"] == "002"
    assert campaign["tasks"][1]["slug"] == "second-task"

    print("  PASS: add-tasks-from-plan")


def test_update_task_requires_workspace(fixture):
    """update-task <seq> complete: Requires workspace file."""
    fixture.cmd('campaign "update test"')
    fixture.cmd('add-task 1 test-task')

    # Should fail without workspace file
    code, out, err = fixture.cmd('update-task 001 complete')
    assert code != 0, "Should fail without workspace"
    assert "no workspace file" in err.lower()

    # Create workspace file, should succeed
    Path(f"{fixture.tmpdir}/workspace/001_test-task_complete.md").write_text("# Test")
    code, out, err = fixture.cmd('update-task 001 complete')
    assert code == 0, f"Should succeed with workspace: {err}"

    print("  PASS: update-task workspace gate")


def test_update_task_normalizes_seq(fixture):
    """update-task normalizes seq input ('1' -> '001')."""
    fixture.cmd('campaign "normalize test"')
    fixture.cmd('add-task 5 five-task')

    # Create workspace with normalized name
    Path(f"{fixture.tmpdir}/workspace/005_five-task_complete.md").write_text("# Test")

    # Update with raw "5"
    code, out, err = fixture.cmd('update-task 5 complete')
    assert code == 0, f"Should normalize seq: {err}"
    assert "005" in out

    print("  PASS: update-task normalizes seq")


def test_complete(fixture):
    """complete: Moves campaign to archive."""
    fixture.cmd('campaign "complete test"')

    code, out, err = fixture.cmd('complete')
    assert code == 0, f"complete failed: {err}"
    assert "Completed campaign" in out

    # Verify moved to complete directory
    active = list(Path(f"{fixture.tmpdir}/.ftl/campaigns/active").glob("*.json"))
    complete = list(Path(f"{fixture.tmpdir}/.ftl/campaigns/complete").glob("*.json"))
    assert len(active) == 0
    assert len(complete) == 1

    print("  PASS: complete")


def test_pending(fixture):
    """pending: Lists pending tasks."""
    # Without campaign
    code, out, err = fixture.cmd('pending')
    assert "No pending tasks" in out

    # With pending tasks
    fixture.cmd('campaign "pending test"')
    fixture.cmd('add-task 1 task-one')
    fixture.cmd('add-task 2 task-two')

    code, out, err = fixture.cmd('pending')
    assert code == 0
    assert "001_task-one" in out
    assert "002_task-two" in out

    print("  PASS: pending")


def test_patterns(fixture):
    """patterns: Aggregates pattern usage."""
    code, out, err = fixture.cmd('patterns')
    assert code == 0
    # Empty is valid
    assert "No patterns found" in out or "Pattern usage" in out

    print("  PASS: patterns")


def test_conflicts(fixture):
    """conflicts: Checks workspace conflicts."""
    fixture.cmd('campaign "conflicts test"')

    code, out, err = fixture.cmd('conflicts')
    assert code == 0
    assert "No conflicts detected" in out or "Active files" in out

    print("  PASS: conflicts")


def test_synthesis_status(fixture):
    """synthesis-status: Returns 3-field status."""
    code, out, err = fixture.cmd('synthesis-status')
    assert code == 0
    assert "Complete campaigns:" in out
    assert "Last synthesis:" in out
    assert "Needs synthesis:" in out

    print("  PASS: synthesis-status")


def test_stale_workspace(fixture):
    """stale-workspace [hours]: Optional hours param."""
    # Default hours
    code, out, err = fixture.cmd('stale-workspace')
    assert code == 0

    # Custom hours
    code, out, err = fixture.cmd('stale-workspace 12')
    assert code == 0

    print("  PASS: stale-workspace")


def test_next_seq(fixture):
    """next-seq: Returns next sequence number."""
    code, out, err = fixture.cmd('next-seq')
    assert code == 0
    assert out.strip() == "001"

    # Create workspace file to advance
    Path(f"{fixture.tmpdir}/workspace/001_test_active.md").write_text("# Test")
    code, out, err = fixture.cmd('next-seq')
    assert code == 0
    assert out.strip() == "002"

    print("  PASS: next-seq")


def main():
    lib_path = get_lib_path()
    if not lib_path or not Path(lib_path).exists():
        print("ERROR: FTL_LIB not set or doesn't exist")
        print("Set FTL_LIB environment variable or ensure ~/.config/ftl/paths.sh exists")
        return 1

    print(f"Testing CLI contracts with FTL_LIB={lib_path}\n")

    fixture = TestFixture(lib_path)

    tests = [
        test_campaign_create,
        test_campaign_no_arg,
        test_active,
        test_status,
        test_add_task_two_args,
        test_add_task_rejects_three,
        test_add_tasks_from_plan,
        test_update_task_requires_workspace,
        test_update_task_normalizes_seq,
        test_complete,
        test_pending,
        test_patterns,
        test_conflicts,
        test_synthesis_status,
        test_stale_workspace,
        test_next_seq,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            fixture.setup()
            test(fixture)
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1
        finally:
            fixture.teardown()

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
