"""Test FTL v2 workspace.py operations."""

import json
from pathlib import Path


class TestWorkspaceCreate:
    """Test workspace creation from plan."""

    def test_create_single_task(self, cli, ftl_dir, sample_plan):
        """Create workspace for single task."""
        plan_json = json.dumps(sample_plan)

        code, out, err = cli.workspace("create", "--plan", "-", stdin=plan_json)
        assert code == 0, f"Failed: {err}"
        assert "Created:" in out

        # Verify file exists
        ws_files = list((ftl_dir / ".ftl/workspace").glob("*.xml"))
        assert len(ws_files) == 2  # Two tasks in sample_plan

    def test_create_specific_task(self, cli, ftl_dir, sample_plan):
        """Create workspace for specific task seq."""
        plan_json = json.dumps(sample_plan)

        code, out, err = cli.workspace("create", "--plan", "-", "--task", "002", stdin=plan_json)
        assert code == 0, f"Failed: {err}"

        # Only one workspace created
        ws_files = list((ftl_dir / ".ftl/workspace").glob("*.xml"))
        assert len(ws_files) == 1
        assert "002_second-task" in ws_files[0].name

    def test_create_with_framework_idioms(self, cli, ftl_dir, sample_plan_with_framework):
        """Workspace includes framework idioms."""
        plan_json = json.dumps(sample_plan_with_framework)

        code, out, err = cli.workspace("create", "--plan", "-", stdin=plan_json)
        assert code == 0, f"Failed: {err}"

        # Parse and verify idioms present
        ws_file = list((ftl_dir / ".ftl/workspace").glob("*.xml"))[0]
        code, out, _ = cli.workspace("parse", str(ws_file))
        data = json.loads(out)

        assert data["framework"] == "FastHTML"
        assert "Use @rt decorator" in data["idioms"]["required"]
        assert "Raw HTML strings" in data["idioms"]["forbidden"]

    def test_create_includes_preflight(self, cli, ftl_dir, sample_plan):
        """Workspace includes preflight checks."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Task 002 has preflight
        ws_file = ftl_dir / ".ftl/workspace/002_second-task_active.xml"
        code, out, _ = cli.workspace("parse", str(ws_file))
        data = json.loads(out)

        assert "python -m py_compile main.py" in data["preflight"]

    def test_create_naming_convention(self, cli, ftl_dir, sample_plan):
        """Workspace files follow NNN_slug_status.xml naming."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        ws_files = list((ftl_dir / ".ftl/workspace").glob("*.xml"))
        names = [f.name for f in ws_files]

        assert "001_first-task_active.xml" in names
        assert "002_second-task_active.xml" in names


class TestWorkspaceParse:
    """Test workspace parsing."""

    def test_parse_returns_all_fields(self, cli, ftl_dir, sample_plan):
        """Parse returns all workspace fields."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        ws_file = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace("parse", str(ws_file))
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)

        # Required fields
        assert data["id"] == "001-first-task"
        assert data["status"] == "active"
        assert data["delta"] == ["test_file.py"]
        assert data["verify"] == "pytest test_file.py --collect-only"
        assert data["budget"] == 3
        assert data["delivered"] == ""
        assert "created_at" in data

    def test_parse_nonexistent_fails(self, cli, ftl_dir):
        """Parse nonexistent file fails gracefully."""
        code, out, err = cli.workspace("parse", "/nonexistent.xml")
        assert code != 0


class TestWorkspaceComplete:
    """Test workspace completion."""

    def test_complete_changes_status(self, cli, ftl_dir, sample_plan):
        """Complete changes status and renames file."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        active_file = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace(
            "complete", str(active_file),
            "--delivered", "Implemented the feature"
        )
        assert code == 0, f"Failed: {err}"
        assert "Completed:" in out

        # Active file should be gone
        assert not active_file.exists()

        # Complete file should exist
        complete_file = ftl_dir / ".ftl/workspace/001_first-task_complete.xml"
        assert complete_file.exists()

        # Parse and verify
        code, out, _ = cli.workspace("parse", str(complete_file))
        data = json.loads(out)
        assert data["status"] == "complete"
        assert data["delivered"] == "Implemented the feature"
        assert data["completed_at"] is not None

    def test_complete_requires_delivered(self, cli, ftl_dir, sample_plan):
        """Complete requires --delivered argument."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        active_file = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace("complete", str(active_file))
        assert code != 0
        assert "delivered" in err.lower()


class TestWorkspaceBlock:
    """Test workspace blocking."""

    def test_block_changes_status(self, cli, ftl_dir, sample_plan):
        """Block changes status and renames file."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        active_file = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace(
            "block", str(active_file),
            "--reason", "Budget exhausted without passing tests"
        )
        assert code == 0, f"Failed: {err}"
        assert "Blocked:" in out

        # Active file should be gone
        assert not active_file.exists()

        # Blocked file should exist
        blocked_file = ftl_dir / ".ftl/workspace/001_first-task_blocked.xml"
        assert blocked_file.exists()

        # Parse and verify
        code, out, _ = cli.workspace("parse", str(blocked_file))
        data = json.loads(out)
        assert data["status"] == "blocked"
        assert "BLOCKED:" in data["delivered"]
        assert "Budget exhausted" in data["delivered"]
        assert data["blocked_at"] is not None

    def test_block_requires_reason(self, cli, ftl_dir, sample_plan):
        """Block requires --reason argument."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        active_file = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace("block", str(active_file))
        assert code != 0
        assert "reason" in err.lower()


class TestWorkspaceLifecycle:
    """Test full workspace lifecycle."""

    def test_active_to_complete_lifecycle(self, cli, ftl_dir, sample_plan):
        """Full lifecycle: create -> complete."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Start with active
        active_files = list((ftl_dir / ".ftl/workspace").glob("*_active.xml"))
        assert len(active_files) == 2

        # Complete first task
        cli.workspace(
            "complete",
            str(ftl_dir / ".ftl/workspace/001_first-task_active.xml"),
            "--delivered", "Done"
        )

        # One active, one complete
        active_files = list((ftl_dir / ".ftl/workspace").glob("*_active.xml"))
        complete_files = list((ftl_dir / ".ftl/workspace").glob("*_complete.xml"))
        assert len(active_files) == 1
        assert len(complete_files) == 1

    def test_active_to_blocked_lifecycle(self, cli, ftl_dir, sample_plan):
        """Full lifecycle: create -> block."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Block first task
        cli.workspace(
            "block",
            str(ftl_dir / ".ftl/workspace/001_first-task_active.xml"),
            "--reason", "Failed verification"
        )

        # One active, one blocked
        active_files = list((ftl_dir / ".ftl/workspace").glob("*_active.xml"))
        blocked_files = list((ftl_dir / ".ftl/workspace").glob("*_blocked.xml"))
        assert len(active_files) == 1
        assert len(blocked_files) == 1


class TestWorkspaceDAGLineage:
    """Test workspace multi-parent lineage for DAG dependencies."""

    def test_single_parent_lineage(self, cli, ftl_dir, sample_plan):
        """Single parent lineage works with backwards compatibility."""
        plan_json = json.dumps(sample_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Complete first task
        ws_001 = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace("complete", str(ws_001), "--delivered", "First task done")

        # Now create workspace for second task (depends on 001)
        cli.workspace("create", "--plan", "-", "--task", "002", stdin=plan_json)

        # Parse second workspace
        ws_002 = ftl_dir / ".ftl/workspace/002_second-task_active.xml"
        code, out, _ = cli.workspace("parse", str(ws_002))
        data = json.loads(out)

        # Should have lineage with backwards compatible fields
        assert "lineage" in data
        assert "parent" in data["lineage"]
        assert "prior_delivery" in data["lineage"]
        assert "001_first-task_complete" in data["lineage"]["parent"]
        assert "First task done" in data["lineage"]["prior_delivery"]

        # Should also have new 'parents' list
        assert "parents" in data["lineage"]
        assert len(data["lineage"]["parents"]) == 1

    def test_multi_parent_lineage(self, cli, ftl_dir, sample_dag_plan):
        """Multi-parent lineage includes all parent deliveries."""
        plan_json = json.dumps(sample_dag_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Complete tasks 003 and 004
        ws_003 = ftl_dir / ".ftl/workspace/003_impl-auth_active.xml"
        ws_004 = ftl_dir / ".ftl/workspace/004_impl-api_active.xml"
        cli.workspace("complete", str(ws_003), "--delivered", "Auth implemented with JWT")
        cli.workspace("complete", str(ws_004), "--delivered", "API with REST endpoints")

        # Now create workspace for task 005 (depends on ["003", "004"])
        cli.workspace("create", "--plan", "-", "--task", "005", stdin=plan_json)

        # Parse task 005 workspace
        ws_005 = ftl_dir / ".ftl/workspace/005_integrate_active.xml"
        code, out, _ = cli.workspace("parse", str(ws_005))
        data = json.loads(out)

        # Should have lineage with multiple parents
        assert "lineage" in data
        assert "parents" in data["lineage"]
        parents = data["lineage"]["parents"]

        assert len(parents) == 2

        # Check both parents are present
        seqs = [p["seq"] for p in parents]
        assert "003" in seqs
        assert "004" in seqs

        # Check deliveries are captured
        deliveries = [p["prior_delivery"] for p in parents]
        assert any("Auth" in d or "JWT" in d for d in deliveries)
        assert any("API" in d or "REST" in d for d in deliveries)

        # Backwards compatibility: first parent in old format
        assert "parent" in data["lineage"]
        assert "prior_delivery" in data["lineage"]

    def test_multi_parent_partial_complete(self, cli, ftl_dir, sample_dag_plan):
        """Multi-parent lineage only includes completed parents."""
        plan_json = json.dumps(sample_dag_plan)
        cli.workspace("create", "--plan", "-", stdin=plan_json)

        # Complete only task 003, leave 004 pending
        ws_003 = ftl_dir / ".ftl/workspace/003_impl-auth_active.xml"
        cli.workspace("complete", str(ws_003), "--delivered", "Auth done")

        # Create workspace for task 005 (some deps not complete)
        cli.workspace("create", "--plan", "-", "--task", "005", stdin=plan_json)

        # Parse task 005 workspace
        ws_005 = ftl_dir / ".ftl/workspace/005_integrate_active.xml"
        code, out, _ = cli.workspace("parse", str(ws_005))
        data = json.loads(out)

        # Should have lineage with only completed parent
        assert "lineage" in data
        assert "parents" in data["lineage"]
        parents = data["lineage"]["parents"]

        # Only 003 is complete, so only one parent in lineage
        assert len(parents) == 1
        assert parents[0]["seq"] == "003"
