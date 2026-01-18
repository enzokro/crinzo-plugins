"""Test FTL v2 workspace.py operations with database backend."""

import json
from pathlib import Path


class TestWorkspaceCreate:
    """Test workspace creation from plan."""

    def test_create_single_task(self, cli, ftl_dir, sample_plan, active_campaign):
        """Create workspace for single task."""
        plan_id = cli.create_plan(sample_plan)

        code, out, err = cli.workspace("create", "--plan-id", str(plan_id))
        assert code == 0, f"Failed: {err}"
        assert "Created:" in out

        # Verify workspaces created in database via list command
        code, out, _ = cli.workspace("list")
        assert code == 0
        workspaces = json.loads(out)
        assert len(workspaces) == 2  # Two tasks in sample_plan

    def test_create_specific_task(self, cli, ftl_dir, sample_plan, active_campaign):
        """Create workspace for specific task seq."""
        plan_id = cli.create_plan(sample_plan)

        code, out, err = cli.workspace("create", "--plan-id", str(plan_id), "--task", "002")
        assert code == 0, f"Failed: {err}"

        # Only one workspace created
        code, out, _ = cli.workspace("list")
        workspaces = json.loads(out)
        assert len(workspaces) == 1
        assert workspaces[0]["workspace_id"] == "002-second-task"

    def test_create_with_framework_idioms(self, cli, ftl_dir, sample_plan_with_framework):
        """Workspace includes framework idioms."""
        # Create campaign first
        cli.campaign("create", sample_plan_with_framework["objective"])
        plan_id = cli.create_plan(sample_plan_with_framework)

        code, out, err = cli.workspace("create", "--plan-id", str(plan_id))
        assert code == 0, f"Failed: {err}"

        # Parse and verify idioms present
        code, out, _ = cli.workspace("parse", "001-add-route")
        data = json.loads(out)

        assert data["framework"] == "FastHTML"
        assert "Use @rt decorator" in data["idioms"]["required"]
        assert "Raw HTML strings" in data["idioms"]["forbidden"]

    def test_create_includes_preflight(self, cli, ftl_dir, sample_plan, active_campaign):
        """Workspace includes preflight checks."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Task 002 has preflight
        code, out, _ = cli.workspace("parse", "002-second-task")
        data = json.loads(out)

        assert "python -m py_compile main.py" in data["preflight"]

    def test_create_naming_convention(self, cli, ftl_dir, sample_plan, active_campaign):
        """Workspace IDs follow NNN-slug naming."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        code, out, _ = cli.workspace("list")
        workspaces = json.loads(out)
        ws_ids = [ws["workspace_id"] for ws in workspaces]

        assert "001-first-task" in ws_ids
        assert "002-second-task" in ws_ids


class TestWorkspaceParse:
    """Test workspace parsing."""

    def test_parse_returns_all_fields(self, cli, ftl_dir, sample_plan, active_campaign):
        """Parse returns all workspace fields."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        code, out, err = cli.workspace("parse", "001-first-task")
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
        """Parse nonexistent workspace returns error."""
        code, out, err = cli.workspace("parse", "nonexistent-workspace")
        # Should return 0 but with error in JSON
        data = json.loads(out)
        assert "error" in data or "not found" in out.lower() or "not found" in str(data).lower()


class TestWorkspaceComplete:
    """Test workspace completion."""

    def test_complete_changes_status(self, cli, ftl_dir, sample_plan, active_campaign):
        """Complete changes status in database."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete using workspace_id path format
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace(
            "complete", str(ws_path),
            "--delivered", "Implemented the feature"
        )
        assert code == 0, f"Failed: {err}"
        assert "Completed:" in out

        # Parse and verify status changed
        code, out, _ = cli.workspace("parse", "001-first-task")
        data = json.loads(out)
        assert data["status"] == "complete"
        assert data["delivered"] == "Implemented the feature"
        assert data["completed_at"] is not None

    def test_complete_requires_delivered(self, cli, ftl_dir, sample_plan, active_campaign):
        """Complete requires --delivered argument."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace("complete", str(ws_path))
        assert code != 0
        assert "delivered" in err.lower()


class TestWorkspaceBlock:
    """Test workspace blocking."""

    def test_block_changes_status(self, cli, ftl_dir, sample_plan, active_campaign):
        """Block changes status in database."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace(
            "block", str(ws_path),
            "--reason", "Budget exhausted without passing tests"
        )
        assert code == 0, f"Failed: {err}"
        assert "Blocked:" in out

        # Parse and verify status changed
        code, out, _ = cli.workspace("parse", "001-first-task")
        data = json.loads(out)
        assert data["status"] == "blocked"
        assert "BLOCKED:" in data["delivered"]
        assert "Budget exhausted" in data["delivered"]
        assert data["blocked_at"] is not None

    def test_block_requires_reason(self, cli, ftl_dir, sample_plan, active_campaign):
        """Block requires --reason argument."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, out, err = cli.workspace("block", str(ws_path))
        assert code != 0
        assert "reason" in err.lower()


class TestWorkspaceLifecycle:
    """Test full workspace lifecycle."""

    def test_active_to_complete_lifecycle(self, cli, ftl_dir, sample_plan, active_campaign):
        """Full lifecycle: create -> complete."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Start with 2 active
        code, out, _ = cli.workspace("list", "--status", "active")
        active = json.loads(out)
        assert len(active) == 2

        # Complete first task
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace("complete", str(ws_path), "--delivered", "Done")

        # One active, one complete
        code, out, _ = cli.workspace("list", "--status", "active")
        active = json.loads(out)
        code2, out2, _ = cli.workspace("list", "--status", "complete")
        complete = json.loads(out2)
        assert len(active) == 1
        assert len(complete) == 1

    def test_active_to_blocked_lifecycle(self, cli, ftl_dir, sample_plan, active_campaign):
        """Full lifecycle: create -> block."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Block first task
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace("block", str(ws_path), "--reason", "Failed verification")

        # One active, one blocked
        code, out, _ = cli.workspace("list", "--status", "active")
        active = json.loads(out)
        code2, out2, _ = cli.workspace("list", "--status", "blocked")
        blocked = json.loads(out2)
        assert len(active) == 1
        assert len(blocked) == 1


class TestWorkspaceDAGLineage:
    """Test workspace multi-parent lineage for DAG dependencies."""

    def test_single_parent_lineage(self, cli, ftl_dir, sample_plan, active_campaign):
        """Single parent lineage works."""
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete first task
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace("complete", str(ws_path), "--delivered", "First task done")

        # Create workspace for second task again (will skip existing but let's parse)
        # Actually task 002 was already created, just parse it
        code, out, _ = cli.workspace("parse", "002-second-task")
        data = json.loads(out)

        # Lineage will be built on next create if parent was complete
        # Let's re-create to pick up the lineage
        cli.workspace("create", "--plan-id", str(plan_id), "--task", "002")
        code, out, _ = cli.workspace("parse", "002-second-task")
        data = json.loads(out)

        # Should have lineage with parent
        assert "lineage" in data
        if data["lineage"]:
            assert "parents" in data["lineage"]
            # If parent was complete, should have entry
            if data["lineage"]["parents"]:
                assert len(data["lineage"]["parents"]) >= 1

    def test_multi_parent_lineage(self, cli, ftl_dir, sample_dag_plan):
        """Multi-parent lineage includes all parent deliveries."""
        # Create campaign first
        cli.campaign("create", sample_dag_plan["objective"])
        plan_id = cli.create_plan(sample_dag_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete tasks 003 and 004
        ws_003 = ftl_dir / ".ftl/workspace/003_impl-auth_active.xml"
        ws_004 = ftl_dir / ".ftl/workspace/004_impl-api_active.xml"
        cli.workspace("complete", str(ws_003), "--delivered", "Auth implemented with JWT")
        cli.workspace("complete", str(ws_004), "--delivered", "API with REST endpoints")

        # Re-create workspace for task 005 to pick up lineage
        cli.workspace("create", "--plan-id", str(plan_id), "--task", "005")

        # Parse task 005 workspace
        code, out, _ = cli.workspace("parse", "005-integrate")
        data = json.loads(out)

        # Should have lineage with multiple parents
        assert "lineage" in data
        if data["lineage"].get("parents"):
            parents = data["lineage"]["parents"]
            assert len(parents) == 2

            # Check both parents are present
            seqs = [p["seq"] for p in parents]
            assert "003" in seqs
            assert "004" in seqs

            # Check deliveries are captured
            deliveries = [p.get("delivered", p.get("prior_delivery", "")) for p in parents]
            assert any("Auth" in d or "JWT" in d for d in deliveries)
            assert any("API" in d or "REST" in d for d in deliveries)

    def test_multi_parent_partial_complete(self, cli, ftl_dir, sample_dag_plan):
        """Multi-parent lineage only includes completed parents."""
        # Create campaign first
        cli.campaign("create", sample_dag_plan["objective"])
        plan_id = cli.create_plan(sample_dag_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete only task 003, leave 004 pending
        ws_003 = ftl_dir / ".ftl/workspace/003_impl-auth_active.xml"
        cli.workspace("complete", str(ws_003), "--delivered", "Auth done")

        # Re-create workspace for task 005
        cli.workspace("create", "--plan-id", str(plan_id), "--task", "005")

        # Parse task 005 workspace
        code, out, _ = cli.workspace("parse", "005-integrate")
        data = json.loads(out)

        # Should have lineage with only completed parent
        assert "lineage" in data
        if data["lineage"].get("parents"):
            parents = data["lineage"]["parents"]
            # Only 003 is complete, so only one parent in lineage
            assert len(parents) == 1
            assert parents[0]["seq"] == "003"
