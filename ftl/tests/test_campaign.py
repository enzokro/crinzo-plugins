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
