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

    def test_create_writes_file(self, cli, ftl_dir):
        """Create writes campaign.json file."""
        cli.campaign("create", "Test objective")

        campaign_file = ftl_dir / ".ftl/campaign.json"
        assert campaign_file.exists()

        data = json.loads(campaign_file.read_text())
        assert data["objective"] == "Test objective"


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
    """Test campaign archival on complete."""

    def test_complete_creates_archive_file(self, cli, ftl_dir):
        """Complete creates archive file in .ftl/archive/."""
        cli.campaign("create", "Archive test")
        cli.campaign("complete", "--summary", "Done")

        archive_dir = ftl_dir / ".ftl/archive"
        assert archive_dir.exists(), "Archive directory not created"
        assert list(archive_dir.glob("*.json")), "No archive file created"

    def test_archive_filename_is_timestamp(self, cli, ftl_dir):
        """Archive filename based on completed_at timestamp."""
        cli.campaign("create", "Timestamp test")
        cli.campaign("complete", "--summary", "Done")

        archive_dir = ftl_dir / ".ftl/archive"
        archive_files = list(archive_dir.glob("*.json"))
        assert archive_files, "No archive file found"

        # Filename should be ISO timestamp format (YYYY-MM-DDTHH-MM-SS)
        filename = archive_files[0].stem
        assert len(filename) >= 19, f"Filename too short: {filename}"
        # Check format: starts with date pattern
        assert filename[4] == "-" and filename[7] == "-", f"Bad date format: {filename}"

    def test_archive_contains_campaign_data(self, cli, ftl_dir):
        """Archived JSON contains full campaign data."""
        cli.campaign("create", "Data test")
        cli.campaign("complete", "--summary", "All done")

        archive_dir = ftl_dir / ".ftl/archive"
        archive_files = list(archive_dir.glob("*.json"))
        assert archive_files, "No archive file found"

        data = json.loads(archive_files[0].read_text())
        assert data["objective"] == "Data test"
        assert data["summary"] == "All done"
        assert data["status"] == "complete"
        assert "completed_at" in data


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
        assert archive["summary"] == "First done"
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
