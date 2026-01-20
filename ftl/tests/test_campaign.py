"""Test FTL v2 campaign.py operations."""

import json
from pathlib import Path


class TestCampaignCreate:
    """Test campaign creation."""

    def test_create_basic(self, cli, ftl_dir):
        """Create campaign with objective."""
        code, out, err = cli.campaign("create", "Build user auth")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["objective"] == "Build user auth"
        assert data["status"] == "active"
        assert data["tasks"] == []
        assert "created_at" in data

    def test_create_with_framework(self, cli, ftl_dir):
        """Create campaign with framework."""
        code, out, err = cli.campaign("create", "Build app", "--framework", "FastHTML")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["framework"] == "FastHTML"

    def test_create_stores_in_database(self, cli, ftl_dir):
        """Create stores campaign in database (queryable via status)."""
        cli.campaign("create", "Test objective")

        # Verify via status command (queries database)
        code, out, _ = cli.campaign("status")
        assert code == 0

        data = json.loads(out)
        assert data["objective"] == "Test objective"
        assert data["status"] == "active"


class TestCampaignStatus:
    """Test campaign status."""

    def test_status_no_campaign(self, cli, ftl_dir):
        """Status returns none when no campaign."""
        code, out, err = cli.campaign("status")
        assert code == 0

        data = json.loads(out)
        assert data["status"] == "none"

    def test_status_with_campaign(self, cli, ftl_dir):
        """Status returns campaign details."""
        cli.campaign("create", "Status test")

        code, out, err = cli.campaign("status")
        assert code == 0

        data = json.loads(out)
        assert data["objective"] == "Status test"
        assert data["status"] == "active"


class TestCampaignExportHistory:
    """Test campaign history export with date range filtering."""

    def test_export_creates_file(self, cli, ftl_dir, tmp_path):
        """Export history creates JSON file."""
        cli.campaign("create", "Export test")
        export_file = tmp_path / "history.json"

        code, out, err = cli.campaign("export", str(export_file))
        assert code == 0, f"Failed: {err}"
        assert export_file.exists()

        data = json.loads(export_file.read_text())
        assert "campaigns" in data

    def test_export_filter_start_date(self, cli, ftl_dir, tmp_path):
        """Export filters campaigns after start date."""
        cli.campaign("create", "Filter start test")
        export_file = tmp_path / "history.json"

        code, out, err = cli.campaign(
            "export", str(export_file), "--start", "2026-01-01"
        )
        assert code == 0, f"Failed: {err}"

        data = json.loads(export_file.read_text())
        assert "campaigns" in data

    def test_export_filter_end_date(self, cli, ftl_dir, tmp_path):
        """Export filters campaigns before end date."""
        cli.campaign("create", "Filter end test")
        export_file = tmp_path / "history.json"

        code, out, err = cli.campaign(
            "export", str(export_file), "--end", "2026-12-31"
        )
        assert code == 0, f"Failed: {err}"

        data = json.loads(export_file.read_text())
        assert "campaigns" in data

    def test_export_filter_both_dates(self, cli, ftl_dir, tmp_path):
        """Export filters campaigns within date range."""
        cli.campaign("create", "Filter both test")
        export_file = tmp_path / "history.json"

        code, out, err = cli.campaign(
            "export", str(export_file),
            "--start", "2026-01-01",
            "--end", "2026-12-31"
        )
        assert code == 0, f"Failed: {err}"

        data = json.loads(export_file.read_text())
        assert "campaigns" in data


class TestCampaignArchive:
    """Test campaign archival on complete (via database)."""

    def test_complete_creates_archive_entry(self, cli, ftl_dir):
        """Complete creates archive entry in database."""
        cli.campaign("create", "Archive test")
        cli.campaign("complete", "--summary", "Done")

        # Verify via history command (queries archive table)
        code, out, _ = cli.campaign("history")
        assert code == 0

        data = json.loads(out)
        assert len(data["archives"]) == 1, "No archive entry created"

    def test_archive_has_timestamp(self, cli, ftl_dir):
        """Archive entry has completed_at timestamp."""
        cli.campaign("create", "Timestamp test")
        cli.campaign("complete", "--summary", "Done")

        code, out, _ = cli.campaign("history")
        data = json.loads(out)
        assert len(data["archives"]) == 1, "No archive entry found"

        archive = data["archives"][0]
        assert "completed_at" in archive
        # Verify timestamp format: starts with date pattern (YYYY-MM-DD)
        completed_at = archive["completed_at"]
        assert len(completed_at) >= 19, f"Timestamp too short: {completed_at}"
        assert completed_at[4] == "-" and completed_at[7] == "-", f"Bad date format: {completed_at}"

    def test_archive_contains_campaign_data(self, cli, ftl_dir):
        """Archive entry contains full campaign data."""
        cli.campaign("create", "Data test")
        cli.campaign("complete", "--summary", "All done")

        code, out, _ = cli.campaign("history")
        data = json.loads(out)
        assert len(data["archives"]) == 1, "No archive entry found"

        archive = data["archives"][0]
        assert archive["objective"] == "Data test"
        # Summary is stored as dict with text field
        assert archive["summary"]["text"] == "All done"
        assert "completed_at" in archive


class TestCampaignHistory:
    """Test campaign history listing."""

    def test_history_empty_when_no_archives(self, cli, ftl_dir):
        """History returns empty list when no archives exist."""
        code, out, err = cli.campaign("history")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["archives"] == []

    def test_history_returns_archived_campaigns(self, cli, ftl_dir):
        """History lists archives with objective, completed_at, summary."""
        cli.campaign("create", "First campaign")
        cli.campaign("complete", "--summary", "First done")

        code, out, err = cli.campaign("history")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert len(data["archives"]) == 1
        archive = data["archives"][0]
        assert archive["objective"] == "First campaign"
        # Summary is stored as dict with text field
        assert archive["summary"]["text"] == "First done"
        assert "completed_at" in archive

    def test_history_sorted_by_date(self, cli, ftl_dir):
        """History sorted by date, most recent first."""
        # Create and complete multiple campaigns
        cli.campaign("create", "Older campaign")
        cli.campaign("complete", "--summary", "Older done")

        cli.campaign("create", "Newer campaign")
        cli.campaign("complete", "--summary", "Newer done")

        code, out, err = cli.campaign("history")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert len(data["archives"]) == 2
        # Most recent should be first
        assert data["archives"][0]["objective"] == "Newer campaign"
        assert data["archives"][1]["objective"] == "Older campaign"


class TestCampaignActive:
    """Test campaign active query."""

    def test_active_no_campaign(self, cli, ftl_dir):
        """Active returns null when no campaign."""
        code, out, err = cli.campaign("active")
        assert code == 0
        assert out.strip() == "null"

    def test_active_with_campaign(self, cli, ftl_dir):
        """Active returns campaign when active."""
        cli.campaign("create", "Active test")

        code, out, err = cli.campaign("active")
        assert code == 0

        data = json.loads(out)
        assert data["objective"] == "Active test"

    def test_active_returns_null_after_complete(self, cli, ftl_dir):
        """Active returns null after campaign complete."""
        cli.campaign("create", "Complete test")
        cli.campaign("complete")

        code, out, err = cli.campaign("active")
        assert code == 0
        assert out.strip() == "null"


class TestCampaignAddTasks:
    """Test adding tasks from plan."""

    def test_add_tasks_from_plan(self, cli, ftl_dir, sample_plan):
        """Add tasks from plan JSON."""
        cli.campaign("create", "Task test")

        plan_json = json.dumps(sample_plan)
        code, out, err = cli.campaign("add-tasks", stdin=plan_json)
        assert code == 0, f"Failed: {err}"

        # Verify tasks added
        code, out, _ = cli.campaign("status")
        data = json.loads(out)
        assert len(data["tasks"]) == 2
        assert data["tasks"][0]["seq"] == "001"
        assert data["tasks"][0]["slug"] == "first-task"
        assert data["tasks"][1]["seq"] == "002"

    def test_add_tasks_sets_framework(self, cli, ftl_dir, sample_plan_with_framework):
        """Add tasks updates campaign framework."""
        cli.campaign("create", "Framework test")

        plan_json = json.dumps(sample_plan_with_framework)
        cli.campaign("add-tasks", stdin=plan_json)

        code, out, _ = cli.campaign("status")
        data = json.loads(out)
        assert data["framework"] == "FastHTML"

    def test_add_tasks_requires_campaign(self, cli, ftl_dir, sample_plan):
        """Add tasks fails without active campaign."""
        plan_json = json.dumps(sample_plan)
        code, out, err = cli.campaign("add-tasks", stdin=plan_json)
        assert code != 0


class TestCampaignUpdateTask:
    """Test task status updates."""

    def test_update_task_status(self, cli, ftl_dir, sample_plan):
        """Update task status."""
        cli.campaign("create", "Update test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))

        code, out, err = cli.campaign("update-task", "001", "in_progress")
        assert code == 0, f"Failed: {err}"

        # Verify updated
        code, out, _ = cli.campaign("status")
        data = json.loads(out)
        assert data["tasks"][0]["status"] == "in_progress"
        assert "updated_at" in data["tasks"][0]

    def test_update_task_complete(self, cli, ftl_dir, sample_plan):
        """Update task to complete."""
        cli.campaign("create", "Complete test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))

        cli.campaign("update-task", "001", "complete")

        code, out, _ = cli.campaign("status")
        data = json.loads(out)
        assert data["tasks"][0]["status"] == "complete"

    def test_update_task_blocked(self, cli, ftl_dir, sample_plan):
        """Update task to blocked."""
        cli.campaign("create", "Block test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))

        cli.campaign("update-task", "001", "blocked")

        code, out, _ = cli.campaign("status")
        data = json.loads(out)
        assert data["tasks"][0]["status"] == "blocked"


class TestCampaignNextTask:
    """Test next task query."""

    def test_next_task_returns_first_pending(self, cli, ftl_dir, sample_plan):
        """Next task returns first pending task."""
        cli.campaign("create", "Next test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))

        code, out, err = cli.campaign("next-task")
        assert code == 0

        data = json.loads(out)
        assert data["seq"] == "001"
        assert data["status"] == "pending"

    def test_next_task_skips_completed(self, cli, ftl_dir, sample_plan):
        """Next task skips completed tasks."""
        cli.campaign("create", "Skip test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))
        cli.campaign("update-task", "001", "complete")

        code, out, _ = cli.campaign("next-task")
        data = json.loads(out)
        assert data["seq"] == "002"

    def test_next_task_returns_null_when_done(self, cli, ftl_dir, sample_plan):
        """Next task returns null when all complete."""
        cli.campaign("create", "Done test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "002", "complete")

        code, out, _ = cli.campaign("next-task")
        assert out.strip() == "null"


class TestCampaignComplete:
    """Test campaign completion."""

    def test_complete_changes_status(self, cli, ftl_dir, sample_plan):
        """Complete changes campaign status."""
        cli.campaign("create", "Complete test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "002", "complete")

        code, out, err = cli.campaign("complete")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["status"] == "complete"
        assert "completed_at" in data

    def test_complete_includes_summary(self, cli, ftl_dir, sample_plan):
        """Complete includes task summary."""
        cli.campaign("create", "Summary test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_plan))
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "002", "blocked")

        code, out, _ = cli.campaign("complete")
        data = json.loads(out)

        assert data["summary"]["total"] == 2
        assert data["summary"]["complete"] == 1
        assert data["summary"]["blocked"] == 1

    def test_complete_requires_campaign(self, cli, ftl_dir):
        """Complete fails without active campaign."""
        code, out, err = cli.campaign("complete")
        assert code != 0


class TestCampaignReadyTasks:
    """Test ready-tasks for DAG-based parallel execution."""

    def test_ready_tasks_returns_no_deps(self, cli, ftl_dir, sample_dag_plan):
        """Ready tasks returns tasks with no dependencies initially."""
        cli.campaign("create", "DAG test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        code, out, err = cli.campaign("ready-tasks")
        assert code == 0, f"Failed: {err}"

        tasks = json.loads(out)
        # Initially, only tasks 001 and 002 should be ready (no deps)
        seqs = [t["seq"] for t in tasks]
        assert "001" in seqs
        assert "002" in seqs
        assert len(tasks) == 2  # Only the two independent spec tasks

    def test_ready_tasks_after_one_complete(self, cli, ftl_dir, sample_dag_plan):
        """Ready tasks includes dependent task after parent completes."""
        cli.campaign("create", "DAG test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete task 001
        cli.campaign("update-task", "001", "complete")

        code, out, _ = cli.campaign("ready-tasks")
        tasks = json.loads(out)
        seqs = [t["seq"] for t in tasks]

        # Now 002 (still pending) and 003 (depends on 001 which is complete)
        assert "002" in seqs
        assert "003" in seqs
        assert "001" not in seqs  # Already complete
        assert "004" not in seqs  # Depends on 002 which is pending
        assert "005" not in seqs  # Depends on both 003 and 004

    def test_ready_tasks_multi_parent(self, cli, ftl_dir, sample_dag_plan):
        """Ready tasks handles multi-parent dependencies correctly."""
        cli.campaign("create", "DAG multi-parent test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete both branches
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "002", "complete")
        cli.campaign("update-task", "003", "complete")
        cli.campaign("update-task", "004", "complete")

        code, out, _ = cli.campaign("ready-tasks")
        tasks = json.loads(out)
        seqs = [t["seq"] for t in tasks]

        # Now task 005 should be ready (depends on both 003 and 004, both complete)
        assert "005" in seqs
        assert len(tasks) == 1

    def test_ready_tasks_multi_parent_partial(self, cli, ftl_dir, sample_dag_plan):
        """Ready tasks waits for ALL parents in multi-parent deps."""
        cli.campaign("create", "DAG partial test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete only one branch (003 depends on 001)
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "003", "complete")
        # Leave 002 and 004 pending

        code, out, _ = cli.campaign("ready-tasks")
        tasks = json.loads(out)
        seqs = [t["seq"] for t in tasks]

        # 005 should NOT be ready (needs both 003 AND 004)
        assert "005" not in seqs
        # 002 should be ready (no deps)
        assert "002" in seqs
        # 004 should NOT be ready (depends on 002 which is pending)
        assert "004" not in seqs

    def test_ready_tasks_empty_when_done(self, cli, ftl_dir, sample_dag_plan):
        """Ready tasks returns empty when all tasks complete."""
        cli.campaign("create", "DAG complete test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete all tasks
        for seq in ["001", "002", "003", "004", "005"]:
            cli.campaign("update-task", seq, "complete")

        code, out, _ = cli.campaign("ready-tasks")
        tasks = json.loads(out)

        assert tasks == []

    def test_add_tasks_stores_depends(self, cli, ftl_dir, sample_dag_plan):
        """Add tasks stores depends field for DAG scheduling."""
        cli.campaign("create", "DAG depends test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        code, out, _ = cli.campaign("status")
        data = json.loads(out)

        # Check that depends is stored
        task_005 = next(t for t in data["tasks"] if t["seq"] == "005")
        assert task_005["depends"] == ["003", "004"]

        task_001 = next(t for t in data["tasks"] if t["seq"] == "001")
        assert task_001["depends"] == "none"


class TestCycleDetection:
    """Test DAG cycle detection."""

    def test_cyclic_plan_rejected(self, cli, ftl_dir):
        """Plans with cyclic dependencies are rejected."""
        cyclic_plan = {
            "campaign": "cyclic",
            "framework": "none",
            "idioms": {"required": [], "forbidden": []},
            "tasks": [
                {"seq": "001", "slug": "a", "type": "BUILD", "delta": ["a.py"],
                 "verify": "true", "budget": 3, "depends": "002"},  # A depends on B
                {"seq": "002", "slug": "b", "type": "BUILD", "delta": ["b.py"],
                 "verify": "true", "budget": 3, "depends": "001"},  # B depends on A
            ]
        }

        cli.campaign("create", "Cycle test")
        code, out, err = cli.campaign("add-tasks", stdin=json.dumps(cyclic_plan))

        # Should fail with cycle error
        assert code != 0
        assert "cycle" in (out + err).lower()

    def test_self_referential_rejected(self, cli, ftl_dir):
        """Task depending on itself is rejected."""
        self_ref_plan = {
            "campaign": "self-ref",
            "framework": "none",
            "idioms": {"required": [], "forbidden": []},
            "tasks": [
                {"seq": "001", "slug": "self", "type": "BUILD", "delta": ["a.py"],
                 "verify": "true", "budget": 3, "depends": "001"},  # Depends on itself
            ]
        }

        cli.campaign("create", "Self-ref test")
        code, out, err = cli.campaign("add-tasks", stdin=json.dumps(self_ref_plan))

        assert code != 0
        assert "cycle" in (out + err).lower()

    def test_multi_hop_cycle_rejected(self, cli, ftl_dir):
        """Multi-hop cycles (A->B->C->A) are detected."""
        multi_hop_plan = {
            "campaign": "multi-hop",
            "framework": "none",
            "idioms": {"required": [], "forbidden": []},
            "tasks": [
                {"seq": "001", "slug": "a", "type": "BUILD", "delta": ["a.py"],
                 "verify": "true", "budget": 3, "depends": "003"},  # A depends on C
                {"seq": "002", "slug": "b", "type": "BUILD", "delta": ["b.py"],
                 "verify": "true", "budget": 3, "depends": "001"},  # B depends on A
                {"seq": "003", "slug": "c", "type": "BUILD", "delta": ["c.py"],
                 "verify": "true", "budget": 3, "depends": "002"},  # C depends on B
            ]
        }

        cli.campaign("create", "Multi-hop cycle test")
        code, out, err = cli.campaign("add-tasks", stdin=json.dumps(multi_hop_plan))

        assert code != 0
        assert "cycle" in (out + err).lower()

    def test_acyclic_dag_accepted(self, cli, ftl_dir, sample_dag_plan):
        """Valid DAG without cycles is accepted."""
        cli.campaign("create", "Acyclic test")
        code, out, err = cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        assert code == 0, f"Failed: {err}"


class TestCascadeHandling:
    """Test cascade status detection and block propagation."""

    def test_cascade_status_no_campaign(self, cli, ftl_dir):
        """Cascade status returns none when no campaign."""
        code, out, _ = cli.campaign("cascade-status")
        assert code == 0

        data = json.loads(out)
        assert data["state"] == "none"

    def test_cascade_status_in_progress(self, cli, ftl_dir, sample_dag_plan):
        """Cascade status shows in_progress when tasks are ready."""
        cli.campaign("create", "Cascade test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        code, out, _ = cli.campaign("cascade-status")
        data = json.loads(out)

        assert data["state"] == "in_progress"
        assert data["ready"] >= 1  # At least one task ready (001 or 002)
        assert data["pending"] >= 1

    def test_cascade_status_stuck(self, cli, ftl_dir, sample_dag_plan):
        """Cascade status detects stuck campaign when ALL root tasks are blocked."""
        cli.campaign("create", "Stuck test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Block BOTH root tasks - this makes ALL children unreachable
        # (blocking only 001 leaves 002 ready, so campaign isn't stuck)
        cli.campaign("update-task", "001", "blocked")
        cli.campaign("update-task", "002", "blocked")

        code, out, _ = cli.campaign("cascade-status")
        data = json.loads(out)

        assert data["state"] == "stuck"
        assert data["blocked"] == 2
        assert len(data["unreachable"]) >= 1

        # Tasks 003, 004 should be unreachable (depend on blocked parents)
        unreachable_seqs = [u["seq"] for u in data["unreachable"]]
        assert "003" in unreachable_seqs or "004" in unreachable_seqs

    def test_cascade_status_complete(self, cli, ftl_dir, sample_dag_plan):
        """Cascade status shows complete when all tasks done."""
        cli.campaign("create", "Complete cascade test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete all tasks
        for seq in ["001", "002", "003", "004", "005"]:
            cli.campaign("update-task", seq, "complete")

        code, out, _ = cli.campaign("cascade-status")
        data = json.loads(out)

        assert data["state"] == "complete"
        assert data["pending"] == 0
        assert data["complete"] == 5

    def test_propagate_blocks_marks_unreachable(self, cli, ftl_dir, sample_dag_plan):
        """Propagate blocks marks unreachable tasks as blocked."""
        cli.campaign("create", "Propagate test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Block BOTH root tasks to make campaign stuck (no ready tasks)
        # Propagation only works when campaign is in "stuck" state
        cli.campaign("update-task", "001", "blocked")
        cli.campaign("update-task", "002", "blocked")

        # Propagate blocks
        code, out, _ = cli.campaign("propagate-blocks")
        assert code == 0

        # Check that propagation occurred
        assert "003" in out or "004" in out or "Propagated" in out

        # Verify tasks are now blocked
        code, status_out, _ = cli.campaign("status")
        data = json.loads(status_out)

        task_003 = next(t for t in data["tasks"] if t["seq"] == "003")
        assert task_003["status"] == "blocked"
        assert "blocked_by" in task_003

    def test_propagate_blocks_cascades_fully(self, cli, ftl_dir, sample_dag_plan):
        """Propagate blocks handles multi-level cascades."""
        cli.campaign("create", "Multi-cascade test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Block BOTH root tasks to trigger cascade propagation
        # (blocking only one leaves the other branch ready)
        cli.campaign("update-task", "001", "blocked")
        cli.campaign("update-task", "002", "blocked")

        # Propagate should handle full cascade: 001,002 blocked -> 003,004 unreachable -> 005 unreachable
        cli.campaign("propagate-blocks")

        # Check that all dependent tasks are now blocked
        task_statuses = {}
        status_code, status_out, _ = cli.campaign("status")
        for t in json.loads(status_out)["tasks"]:
            task_statuses[t["seq"]] = t["status"]

        assert task_statuses["001"] == "blocked"
        assert task_statuses["002"] == "blocked"
        assert task_statuses["003"] == "blocked"
        assert task_statuses["004"] == "blocked"
        assert task_statuses["005"] == "blocked"  # Cascaded from both parents

    def test_propagate_blocks_no_action_when_not_stuck(self, cli, ftl_dir, sample_dag_plan):
        """Propagate blocks does nothing when campaign not stuck."""
        cli.campaign("create", "No propagate test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Don't block anything - just run propagate
        code, out, _ = cli.campaign("propagate-blocks")
        assert code == 0
        assert "No blocks to propagate" in out


class TestMergeRevisedPlan:
    """Test merge_revised_plan for plan revision."""

    def test_merge_basic(self, cli, ftl_dir, sample_dag_plan, tmp_path):
        """Basic merge updates task dependencies."""
        cli.campaign("create", "Merge test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Create revised plan
        revised = {
            "tasks": [
                {"seq": "003", "depends": "none"},  # Change dependency
            ]
        }
        revised_path = tmp_path / "revised.json"
        revised_path.write_text(json.dumps(revised))

        code, out, err = cli.campaign("merge-revised-plan", str(revised_path))
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["merged"] >= 1

    def test_merge_preserves_complete_tasks(self, cli, ftl_dir, sample_dag_plan, tmp_path):
        """Merge skips completed tasks."""
        cli.campaign("create", "Preserve test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))
        cli.campaign("update-task", "001", "complete")

        # Try to revise completed task
        revised = {
            "tasks": [
                {"seq": "001", "depends": "002"},  # Try to change deps
            ]
        }
        revised_path = tmp_path / "revised.json"
        revised_path.write_text(json.dumps(revised))

        code, out, _ = cli.campaign("merge-revised-plan", str(revised_path))
        assert code == 0

        data = json.loads(out)
        assert data["unchanged"] >= 1

        # Verify task 001 unchanged
        code, status_out, _ = cli.campaign("status")
        status_data = json.loads(status_out)
        task_001 = next(t for t in status_data["tasks"] if t["seq"] == "001")
        assert task_001["status"] == "complete"

    def test_merge_rejects_cycle(self, cli, ftl_dir, sample_dag_plan, tmp_path):
        """Merge rejects plan that would create cycle."""
        cli.campaign("create", "Cycle reject test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Create cyclic revision: 001 depends on 003, 003 depends on 001
        revised = {
            "tasks": [
                {"seq": "001", "depends": "003"},  # Creates cycle with 003->001
            ]
        }
        revised_path = tmp_path / "revised.json"
        revised_path.write_text(json.dumps(revised))

        code, out, err = cli.campaign("merge-revised-plan", str(revised_path))

        # Should detect cycle and not apply changes
        combined = out + err
        assert "cycle" in combined.lower() or "error" in combined.lower()

    def test_merge_unblocks_tasks(self, cli, ftl_dir, sample_dag_plan, tmp_path):
        """Merge resets blocked tasks to pending on dependency change."""
        cli.campaign("create", "Unblock test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))
        cli.campaign("update-task", "003", "blocked")

        # Revise task 003 dependencies
        revised = {
            "tasks": [
                {"seq": "003", "depends": "none"},
            ]
        }
        revised_path = tmp_path / "revised.json"
        revised_path.write_text(json.dumps(revised))

        cli.campaign("merge-revised-plan", str(revised_path))

        # Verify task is now pending
        code, status_out, _ = cli.campaign("status")
        status_data = json.loads(status_out)
        task_003 = next(t for t in status_data["tasks"] if t["seq"] == "003")
        assert task_003["status"] == "pending"

    def test_merge_atomicity(self, cli, ftl_dir, sample_dag_plan, tmp_path):
        """Merge is atomic: cycle detection prevents partial update."""
        cli.campaign("create", "Atomicity test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Get original state
        code, orig_out, _ = cli.campaign("status")
        orig_data = json.loads(orig_out)
        orig_tasks = {t["seq"]: t.get("depends", "none") for t in orig_data["tasks"]}

        # Attempt merge that would create cycle (should fail)
        revised = {
            "tasks": [
                {"seq": "002", "depends": "none"},  # Valid change
                {"seq": "001", "depends": "003"},   # Would create cycle
            ]
        }
        revised_path = tmp_path / "revised.json"
        revised_path.write_text(json.dumps(revised))

        cli.campaign("merge-revised-plan", str(revised_path))

        # Verify original state preserved (atomic rollback)
        code, after_out, _ = cli.campaign("status")
        after_data = json.loads(after_out)
        after_tasks = {t["seq"]: t.get("depends", "none") for t in after_data["tasks"]}

        # Dependencies should be unchanged due to cycle rejection
        assert orig_tasks["002"] == after_tasks["002"]


class TestConcurrency:
    """Test thread safety and concurrency handling."""

    def test_concurrent_task_updates(self, ftl_dir):
        """Concurrent update_task calls don't lose updates."""
        import sys
        ftl_path = str(Path(__file__).parent.parent)
        if ftl_path not in sys.path:
            sys.path.insert(0, ftl_path)

        from lib.campaign import create, add_tasks, update_task, status
        from lib.db import reset_db
        import threading
        import time

        reset_db()

        # Create campaign with tasks
        create("Concurrency test")
        plan = {
            "tasks": [
                {"seq": str(i).zfill(3), "slug": f"task-{i}", "type": "BUILD",
                 "delta": [f"t{i}.py"], "verify": "true", "budget": 3, "depends": "none"}
                for i in range(1, 11)  # 10 tasks
            ]
        }
        add_tasks(plan)

        # Concurrent updates
        errors = []
        def update_worker(seq, target_status):
            try:
                update_task(seq, target_status)
            except Exception as e:
                errors.append((seq, str(e)))

        threads = []
        for i in range(1, 11):
            seq = str(i).zfill(3)
            t = threading.Thread(target=update_worker, args=(seq, "complete"))
            threads.append(t)

        # Start all threads at roughly the same time
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify no errors and all updates applied
        assert len(errors) == 0, f"Update errors: {errors}"

        campaign = status()
        completed = sum(1 for t in campaign["tasks"] if t["status"] == "complete")
        assert completed == 10, f"Expected 10 complete, got {completed}"

    def test_concurrent_db_init(self, tmp_path):
        """Database initialization is thread-safe."""
        import sys
        import os
        ftl_path = str(Path(__file__).parent.parent)
        if ftl_path not in sys.path:
            sys.path.insert(0, ftl_path)

        # Use temp database
        test_db = tmp_path / "concurrent_test.db"
        os.environ['FTL_DB_PATH'] = str(test_db)

        # Force reimport to test fresh init
        import importlib
        from lib.db import connection
        connection._db = None  # Reset singleton

        import threading

        errors = []
        connections = []

        def init_worker():
            try:
                from lib.db import get_db
                db = get_db()
                connections.append(id(db))
            except Exception as e:
                errors.append(str(e))

        # Start multiple threads trying to init simultaneously
        threads = [threading.Thread(target=init_worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Clean up
        os.environ.pop('FTL_DB_PATH', None)

        # All threads should get same database instance (singleton)
        assert len(errors) == 0, f"Init errors: {errors}"
        assert len(set(connections)) == 1, "Multiple db instances created"

    def test_concurrent_propagate_blocks(self, ftl_dir):
        """Concurrent propagate_blocks doesn't corrupt state."""
        import sys
        ftl_path = str(Path(__file__).parent.parent)
        if ftl_path not in sys.path:
            sys.path.insert(0, ftl_path)

        from lib.campaign import create, add_tasks, update_task, propagate_blocks, status
        from lib.db import reset_db
        import threading

        reset_db()

        # Create campaign with DAG
        create("Concurrent propagate test")
        plan = {
            "tasks": [
                {"seq": "001", "slug": "root", "type": "BUILD",
                 "delta": ["r.py"], "verify": "true", "budget": 3, "depends": "none"},
                {"seq": "002", "slug": "child1", "type": "BUILD",
                 "delta": ["c1.py"], "verify": "true", "budget": 3, "depends": "001"},
                {"seq": "003", "slug": "child2", "type": "BUILD",
                 "delta": ["c2.py"], "verify": "true", "budget": 3, "depends": "001"},
            ]
        }
        add_tasks(plan)

        # Block root
        update_task("001", "blocked")

        # Concurrent propagation
        results = []
        errors = []

        def propagate_worker():
            try:
                result = propagate_blocks()
                results.append(result)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=propagate_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Propagate errors: {errors}"

        # Verify consistent state
        campaign = status()
        blocked = sum(1 for t in campaign["tasks"] if t["status"] == "blocked")
        assert blocked == 3, f"Expected 3 blocked, got {blocked}"


class TestGetReplanInput:
    """Test get_replan_input for adaptive re-planning."""

    def test_replan_input_no_campaign(self, cli, ftl_dir):
        """get_replan_input returns empty dict when no campaign."""
        code, out, _ = cli.campaign("get-replan-input")
        assert code == 0

        data = json.loads(out)
        assert data == {}

    def test_replan_input_basic(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input returns proper structure."""
        cli.campaign("create", "Replan test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        code, out, _ = cli.campaign("get-replan-input")
        assert code == 0

        data = json.loads(out)
        assert data["mode"] == "replan"
        assert data["objective"] == "Replan test"
        assert "completed_count" in data
        assert "blocked_count" in data
        assert "pending_count" in data
        assert "completed_tasks" in data
        assert "blocked_tasks" in data
        assert "remaining_tasks" in data

    def test_replan_input_counts(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input returns accurate task counts."""
        cli.campaign("create", "Count test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        # Complete task 001, block task 002
        cli.campaign("update-task", "001", "complete")
        cli.campaign("update-task", "002", "blocked")

        code, out, _ = cli.campaign("get-replan-input")
        data = json.loads(out)

        assert data["completed_count"] == 1
        assert data["blocked_count"] == 1
        assert data["pending_count"] == 3  # 003, 004, 005

    def test_replan_input_completed_tasks(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input includes completed task evidence."""
        cli.campaign("create", "Evidence test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))
        cli.campaign("update-task", "001", "complete")

        code, out, _ = cli.campaign("get-replan-input")
        data = json.loads(out)

        assert len(data["completed_tasks"]) == 1
        assert data["completed_tasks"][0]["seq"] == "001"
        assert "slug" in data["completed_tasks"][0]
        assert "delivered" in data["completed_tasks"][0]

    def test_replan_input_blocked_tasks(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input includes blocked task reasons."""
        cli.campaign("create", "Blocked test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))
        cli.campaign("update-task", "001", "blocked")

        code, out, _ = cli.campaign("get-replan-input")
        data = json.loads(out)

        assert len(data["blocked_tasks"]) == 1
        assert data["blocked_tasks"][0]["seq"] == "001"
        assert "reason" in data["blocked_tasks"][0]

    def test_replan_input_remaining_tasks(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input includes remaining pending tasks."""
        cli.campaign("create", "Remaining test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))
        cli.campaign("update-task", "001", "complete")

        code, out, _ = cli.campaign("get-replan-input")
        data = json.loads(out)

        # Should have 4 remaining (002, 003, 004, 005)
        remaining_seqs = [t["seq"] for t in data["remaining_tasks"]]
        assert "002" in remaining_seqs
        assert "003" in remaining_seqs
        assert "004" in remaining_seqs
        assert "005" in remaining_seqs
        assert "001" not in remaining_seqs  # Already complete

    def test_replan_input_preserves_deps(self, cli, ftl_dir, sample_dag_plan):
        """get_replan_input preserves task dependencies."""
        cli.campaign("create", "Deps test")
        cli.campaign("add-tasks", stdin=json.dumps(sample_dag_plan))

        code, out, _ = cli.campaign("get-replan-input")
        data = json.loads(out)

        # Find task 005 in remaining
        task_005 = next((t for t in data["remaining_tasks"] if t["seq"] == "005"), None)
        assert task_005 is not None
        assert task_005["depends"] == ["003", "004"]
