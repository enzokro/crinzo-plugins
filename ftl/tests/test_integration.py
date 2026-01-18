"""Test FTL v2 integration - full workflow tests with database backend."""

import json
from pathlib import Path


class TestFullWorkflow:
    """Test complete Planner -> Builder -> Observer workflow."""

    def test_campaign_to_workspace_flow(self, cli, ftl_dir, sample_plan):
        """Test campaign creation through workspace generation."""
        # 1. Create campaign
        code, out, _ = cli.campaign("create", "Integration test")
        assert code == 0
        campaign = json.loads(out)
        assert campaign["status"] == "active"

        # 2. Add tasks from plan
        plan_json = json.dumps(sample_plan)
        code, out, _ = cli.campaign("add-tasks", stdin=plan_json)
        assert code == 0

        # 3. Create workspaces
        plan_id = cli.create_plan(sample_plan)
        code, out, _ = cli.workspace("create", "--plan-id", str(plan_id))
        assert code == 0

        # 4. Verify workspaces created via database query
        code, out, _ = cli.workspace("list")
        workspaces = json.loads(out)
        assert len(workspaces) == 2

        # 5. Get next task
        code, out, _ = cli.campaign("next-task")
        next_task = json.loads(out)
        assert next_task["seq"] == "001"

    def test_workspace_complete_updates_campaign(self, cli, ftl_dir, sample_plan):
        """Completing workspace should allow campaign task update."""
        # Setup
        cli.campaign("create", "Complete flow test")
        plan_json = json.dumps(sample_plan)
        cli.campaign("add-tasks", stdin=plan_json)
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete workspace using path format
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        code, _, _ = cli.workspace(
            "complete", str(ws_path),
            "--delivered", "Implemented tests"
        )
        assert code == 0

        # Update campaign task
        cli.campaign("update-task", "001", "complete")

        # Next task should be 002
        code, out, _ = cli.campaign("next-task")
        next_task = json.loads(out)
        assert next_task["seq"] == "002"

    def test_blocked_workspace_flow(self, cli, ftl_dir, sample_plan):
        """Blocked workspace should record failure for observer."""
        # Setup
        cli.campaign("create", "Block flow test")
        plan_json = json.dumps(sample_plan)
        cli.campaign("add-tasks", stdin=plan_json)
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Block workspace
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace(
            "block", str(ws_path),
            "--reason", "pytest failed: AssertionError in test_main"
        )

        # Update campaign
        cli.campaign("update-task", "001", "blocked")

        # Verify blocked workspace exists in database
        code, out, _ = cli.workspace("list", "--status", "blocked")
        blocked = json.loads(out)
        assert len(blocked) == 1

        # Parse blocked workspace
        code, out, _ = cli.workspace("parse", blocked[0]["workspace_id"])
        data = json.loads(out)
        assert "AssertionError" in data["delivered"]


class TestMemoryIntegration:
    """Test memory integration with workspace flow."""

    def test_failure_extraction_flow(self, cli, ftl_dir, sample_plan):
        """Observer extracts failures from blocked workspaces."""
        # Setup campaign and workspace
        cli.campaign("create", "Failure test")
        plan_json = json.dumps(sample_plan)
        cli.campaign("add-tasks", stdin=plan_json)
        plan_id = cli.create_plan(sample_plan)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Block workspace with error
        ws_path = ftl_dir / ".ftl/workspace/001_first-task_active.xml"
        cli.workspace(
            "block", str(ws_path),
            "--reason", "ModuleNotFoundError: No module named 'fasthtml'"
        )

        # Observer would extract this - simulate with add-failure
        failure = {
            "name": "missing-fasthtml",
            "trigger": "ModuleNotFoundError: No module named 'fasthtml'",
            "fix": "pip install python-fasthtml",
            "match": "No module named.*fasthtml",
            "cost": 3000,
            "source": ["001-first-task"]
        }
        cli.memory("add-failure", "--json", json.dumps(failure))

        # Verify in memory
        code, out, _ = cli.memory("query", "fasthtml")
        results = json.loads(out)
        assert len(results) == 1
        assert results[0]["type"] == "failure"

    def test_pattern_extraction_flow(self, cli, ftl_dir, sample_plan_with_framework):
        """Observer extracts patterns from completed workspaces."""
        # Setup with framework
        cli.campaign("create", "Pattern test", "--framework", "FastHTML")
        plan_json = json.dumps(sample_plan_with_framework)
        cli.campaign("add-tasks", stdin=plan_json)
        plan_id = cli.create_plan(sample_plan_with_framework)
        cli.workspace("create", "--plan-id", str(plan_id))

        # Complete workspace
        ws_path = ftl_dir / ".ftl/workspace/001_add-route_active.xml"
        cli.workspace(
            "complete", str(ws_path),
            "--delivered", "Added route using @rt decorator and Div components"
        )

        # Observer would extract pattern - simulate
        pattern = {
            "name": "fasthtml-route-pattern",
            "trigger": "Adding route in FastHTML",
            "insight": "Use @rt('/path') decorator and return Div() tree",
            "saved": 5000,
            "source": ["001-add-route"]
        }
        cli.memory("add-pattern", "--json", json.dumps(pattern))

        # Future workspace creation could inject this
        code, out, _ = cli.memory("context", "--all")
        data = json.loads(out)
        assert len(data["patterns"]) == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_plan_tasks(self, cli, ftl_dir):
        """Handle plan with no tasks."""
        # Need to create a campaign first
        cli.campaign("create", "Empty plan test")
        plan = {"campaign": "empty", "framework": "none", "tasks": []}
        plan_id = cli.create_plan(plan)

        code, out, _ = cli.workspace("create", "--plan-id", str(plan_id))
        assert code == 0

        # No workspaces created
        code, out, _ = cli.workspace("list")
        workspaces = json.loads(out)
        assert len(workspaces) == 0

    def test_missing_plan_id_fails(self, cli, ftl_dir):
        """Non-existent plan ID fails gracefully."""
        code, out, err = cli.workspace("create", "--plan-id", "99999")
        assert code != 0

    def test_missing_required_fields(self, cli, ftl_dir):
        """Plan missing required fields fails gracefully."""
        cli.campaign("create", "Incomplete plan test")
        plan = {"campaign": "incomplete"}  # Missing tasks
        plan_id = cli.create_plan(plan)

        code, out, _ = cli.workspace("create", "--plan-id", str(plan_id))
        # Should handle gracefully (create 0 workspaces)
        assert code == 0

    def test_duplicate_seq_different_slug(self, cli, ftl_dir):
        """Different slugs with same seq create separate workspaces."""
        cli.campaign("create", "Duplicate seq test")
        plan = {
            "campaign": "dupe",
            "framework": "none",
            "tasks": [
                {"seq": "001", "slug": "first", "type": "BUILD",
                 "delta": ["a.py"], "verify": "true", "budget": 3, "depends": "none"},
                {"seq": "001", "slug": "second", "type": "BUILD",  # Same seq, different slug
                 "delta": ["b.py"], "verify": "true", "budget": 3, "depends": "none"}
            ]
        }
        plan_id = cli.create_plan(plan)

        code, out, _ = cli.workspace("create", "--plan-id", str(plan_id))

        # Different slugs = different workspaces
        code, out, _ = cli.workspace("list")
        workspaces = json.loads(out)
        assert len(workspaces) == 2
        ws_ids = [ws["workspace_id"] for ws in workspaces]
        assert "001-first" in ws_ids
        assert "001-second" in ws_ids


class TestCLIHelp:
    """Test CLI help and usage."""

    def test_memory_help(self, cli, ftl_dir):
        """Memory help shows subcommands."""
        code, out, err = cli.memory("--help")
        # Help goes to stdout or stderr depending on argparse version
        output = out + err
        assert "context" in output.lower()
        assert "add-failure" in output.lower()
        assert "add-pattern" in output.lower()
        assert "query" in output.lower()

    def test_workspace_help(self, cli, ftl_dir):
        """Workspace help shows subcommands."""
        code, out, err = cli.workspace("--help")
        output = out + err
        assert "create" in output.lower()
        assert "complete" in output.lower()
        assert "block" in output.lower()
        assert "parse" in output.lower()

    def test_campaign_help(self, cli, ftl_dir):
        """Campaign help shows subcommands."""
        code, out, err = cli.campaign("--help")
        output = out + err
        assert "create" in output.lower()
        assert "status" in output.lower()
        assert "add-tasks" in output.lower()
        assert "complete" in output.lower()
