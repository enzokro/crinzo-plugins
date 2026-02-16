"""Tests for build_loop.py - all build loop utilities.

Consolidated from test_dag_utils.py, test_wait.py, test_wave_synthesis.py.
Tests: cycle detection, task readiness, stall detection, wait-polling,
parent deliveries, build_status, explorer timeout dedup.
"""

import json


# ── DAG utilities ──


class TestCycleDetection:
    """Tests for detect_cycles function."""

    def test_detect_no_cycles(self):
        """Valid DAG has no cycles."""
        from lib.build_loop import detect_cycles

        # A -> B -> C (valid DAG)
        dependencies = {
            "A": ["B"],
            "B": ["C"],
            "C": [],
        }

        cycles = detect_cycles(dependencies)

        assert cycles == []

    def test_detect_simple_cycle(self):
        """Detects simple A->B->A cycle."""
        from lib.build_loop import detect_cycles

        dependencies = {
            "A": ["B"],
            "B": ["A"],
        }

        cycles = detect_cycles(dependencies)

        assert len(cycles) >= 1
        # Cycle should contain both A and B
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert "A" in cycle_nodes
        assert "B" in cycle_nodes

    def test_detect_complex_cycle(self):
        """Detects longer A->B->C->A cycle."""
        from lib.build_loop import detect_cycles

        dependencies = {
            "A": ["B"],
            "B": ["C"],
            "C": ["A"],
        }

        cycles = detect_cycles(dependencies)

        assert len(cycles) >= 1
        cycle_nodes = set()
        for cycle in cycles:
            cycle_nodes.update(cycle)
        assert "A" in cycle_nodes
        assert "B" in cycle_nodes
        assert "C" in cycle_nodes

    def test_detect_self_loop(self):
        """Detects self-referential A->A."""
        from lib.build_loop import detect_cycles

        dependencies = {
            "A": ["A"],
            "B": [],
        }

        cycles = detect_cycles(dependencies)

        assert len(cycles) >= 1
        # Should find A in a cycle
        found_self_loop = any("A" in cycle for cycle in cycles)
        assert found_self_loop

    def test_detect_multiple_cycles(self):
        """Detects independent cycles in graph."""
        from lib.build_loop import detect_cycles

        # Two independent cycles
        dependencies = {
            "A": ["B"],
            "B": ["A"],  # Cycle 1
            "C": ["D"],
            "D": ["C"],  # Cycle 2
        }

        cycles = detect_cycles(dependencies)

        # Should find at least 2 cycles
        assert len(cycles) >= 2


# ── Task readiness ──


class TestTaskReadiness:
    """Tests for get_ready_tasks function."""

    def test_get_ready_no_blockers(self, sample_tasks):
        """Pending task with no blockers is ready."""
        from lib.build_loop import get_ready_tasks

        # Modify sample_tasks: task-003 depends on task-002 which is delivered
        tasks = sample_tasks

        ready = get_ready_tasks(tasks)

        # task-003 should be ready (task-002 delivered)
        assert "task-003" in ready

    def test_get_ready_all_delivered(self):
        """Task is ready when all blockers delivered."""
        from lib.build_loop import get_ready_tasks

        tasks = [
            {"id": "t1", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
            {"id": "t2", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
            {"id": "t3", "status": "pending", "blockedBy": ["t1", "t2"], "metadata": {}},
        ]

        ready = get_ready_tasks(tasks)

        assert "t3" in ready

    def test_get_ready_blocker_blocked(self, sample_tasks_with_blocked):
        """Task is not ready if blocker was blocked."""
        from lib.build_loop import get_ready_tasks

        ready = get_ready_tasks(sample_tasks_with_blocked)

        # task-003 depends on task-002 which is blocked
        assert "task-003" not in ready


# ── Stall detection ──


class TestStallDetection:
    """Tests for check_stalled function."""

    def test_check_stalled_has_ready(self, sample_tasks):
        """Not stalled when ready tasks exist."""
        from lib.build_loop import check_stalled

        is_stalled, info = check_stalled(sample_tasks)

        assert is_stalled is False
        assert info is None

    def test_check_stalled_all_blocked(self, sample_tasks_with_blocked):
        """Stalled when pending tasks exist but none ready."""
        from lib.build_loop import check_stalled

        is_stalled, info = check_stalled(sample_tasks_with_blocked)

        assert is_stalled is True
        assert info is not None
        assert info["pending_count"] >= 1
        assert len(info["blocked_by_blocked"]) >= 1

        # Should identify which task is blocked by blocked tasks
        blocked_info = info["blocked_by_blocked"][0]
        assert "task_id" in blocked_info
        assert "blocked_by" in blocked_info


# ── Wait-polling ──


class TestWaitForExplorerResults:
    """Tests for wait_for_explorer_results function."""

    def test_wait_explorer_results_found(self, tmp_path):
        """Returns merged findings when all explorer results arrive."""
        from lib.build_loop import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Write two explorer result files
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/a.py", "what": "module A"}]
        }))
        (results_dir / "agent-2.json").write_text(json.dumps({
            "findings": [{"file": "src/b.py", "what": "module B"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["count"] == 2
        assert len(result["findings"]) == 2

    def test_wait_explorer_results_timeout(self, tmp_path):
        """Returns partial results on timeout."""
        from lib.build_loop import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Only one of two expected
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/a.py", "what": "module A"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=0.3,
            poll_interval=0.1
        )

        assert result["completed"] is False
        assert result["timed_out"] is True
        assert result["count"] == 1

    def test_wait_explorer_deduplicates(self, tmp_path):
        """Deduplicates findings by file path."""
        from lib.build_loop import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Two explorers find the same file
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 1"}]
        }))
        (results_dir / "agent-2.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 2"}]
        }))

        result = wait_for_explorer_results(
            expected_count=2,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert len(result["findings"]) == 1  # Deduped

    def test_wait_explorer_deduplicates_on_timeout(self, tmp_path):
        """Timeout path also deduplicates findings by file path."""
        from lib.build_loop import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        # Two explorers with overlapping findings, but fewer than expected
        (results_dir / "agent-1.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 1"}]
        }))
        (results_dir / "agent-2.json").write_text(json.dumps({
            "findings": [{"file": "src/shared.py", "what": "from agent 2"}]
        }))

        result = wait_for_explorer_results(
            expected_count=5,  # expect 5, only 2 arrived
            helix_dir=str(helix_dir),
            timeout_sec=0.3,
            poll_interval=0.1
        )

        assert result["completed"] is False
        assert result["timed_out"] is True
        assert len(result["findings"]) == 1  # Deduped even on timeout

    def test_wait_explorer_handles_errors(self, tmp_path):
        """Reports errors from failed explorers."""
        from lib.build_loop import wait_for_explorer_results

        helix_dir = tmp_path / ".helix"
        results_dir = helix_dir / "explorer-results"
        results_dir.mkdir(parents=True)

        (results_dir / "agent-1.json").write_text(json.dumps({
            "status": "error", "error": "Scope not found"
        }))

        result = wait_for_explorer_results(
            expected_count=1,
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["errors"] is not None
        assert "Scope not found" in result["errors"][0]


class TestWaitForBuilderResults:
    """Tests for wait_for_builder_results function."""

    def test_wait_builder_unknown_not_delivered(self, tmp_path):
        """Tasks with unknown outcome cause all_delivered=False."""
        from lib.build_loop import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "unknown", "summary": ""}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is False
        assert len(result["unknown"]) == 1
        assert result["unknown"][0]["task_id"] == "task-2"

    def test_wait_builder_all_delivered(self, tmp_path):
        """All delivered tasks => all_delivered=True."""
        from lib.build_loop import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is True
        assert len(result["unknown"]) == 0

    def test_wait_builder_timeout(self, tmp_path):
        """Returns partial results on timeout."""
        from lib.build_loop import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=0.3,
            poll_interval=0.1
        )

        assert result["completed"] is False
        assert result["timed_out"] is True
        assert "task-2" in result["missing"]

    def test_wait_builder_blocked(self, tmp_path):
        """Blocked tasks are categorized correctly."""
        from lib.build_loop import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "blocked", "summary": "tests failed"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["completed"] is True
        assert result["all_delivered"] is False
        assert len(result["blocked"]) == 1
        assert len(result["delivered"]) == 1

    def test_wait_builder_insights_emitted(self, tmp_path):
        """Counts insights_emitted from task status entries."""
        from lib.build_loop import wait_for_builder_results

        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text(
            json.dumps({"task_id": "task-1", "outcome": "delivered", "summary": "done", "insight": "When X, do Y"}) + "\n"
            + json.dumps({"task_id": "task-2", "outcome": "delivered", "summary": "done"}) + "\n"
        )

        result = wait_for_builder_results(
            ["task-1", "task-2"],
            helix_dir=str(helix_dir),
            timeout_sec=1.0,
            poll_interval=0.1
        )

        assert result["insights_emitted"] == 1


# ── Parent deliveries ──


class TestCollectParentDeliveries:
    """Tests for collect_parent_deliveries."""

    def test_maps_deliveries_to_dependent_tasks(self):
        """Correctly maps blocker deliveries to next-wave tasks."""
        from lib.build_loop import collect_parent_deliveries

        wave_results = [
            {"task_id": "001", "outcome": "delivered", "summary": "Created data models"},
            {"task_id": "002", "outcome": "delivered", "summary": "Set up database schema"},
            {"task_id": "003", "outcome": "blocked", "summary": "Missing config"},
        ]
        task_blockers = {
            "004": ["001", "002"],  # task 004 depends on 001 and 002
            "005": ["003"],         # task 005 depends on 003 (blocked)
        }

        deliveries = collect_parent_deliveries(wave_results, task_blockers)

        assert "004" in deliveries
        assert "[001]" in deliveries["004"]
        assert "[002]" in deliveries["004"]
        # Task 003 was blocked, so no delivery for 005
        assert "005" not in deliveries

    def test_empty_blockers_returns_empty(self):
        """No blockers means no parent deliveries."""
        from lib.build_loop import collect_parent_deliveries

        deliveries = collect_parent_deliveries([], {})
        assert deliveries == {}

    def test_missing_blocker_results_skipped(self):
        """Blockers not in wave results are silently skipped."""
        from lib.build_loop import collect_parent_deliveries

        wave_results = [
            {"task_id": "001", "outcome": "delivered", "summary": "Done A"},
        ]
        task_blockers = {
            "003": ["001", "002"],  # 002 not in results
        }

        deliveries = collect_parent_deliveries(wave_results, task_blockers)
        assert "003" in deliveries
        assert "[001]" in deliveries["003"]
        assert "[002]" not in deliveries["003"]

    def test_collect_parent_deliveries_mixed_id_formats(self):
        """Bare '3' blocker matches 'task-3' result via normalization."""
        from lib.build_loop import collect_parent_deliveries

        wave_results = [
            {"task_id": "task-3", "outcome": "delivered", "summary": "Created models"},
        ]
        task_blockers = {
            "5": ["3"],  # bare ID referencing task-3
        }

        deliveries = collect_parent_deliveries(wave_results, task_blockers)
        assert "5" in deliveries
        assert "Created models" in deliveries["5"]

    def test_collect_parent_deliveries_bare_ids(self):
        """Both sides use bare IDs."""
        from lib.build_loop import collect_parent_deliveries

        wave_results = [
            {"task_id": "1", "outcome": "delivered", "summary": "Schema done"},
            {"task_id": "2", "outcome": "delivered", "summary": "Models done"},
        ]
        task_blockers = {
            "3": ["1", "2"],
        }

        deliveries = collect_parent_deliveries(wave_results, task_blockers)
        assert "3" in deliveries
        assert "[1]" in deliveries["3"]
        assert "[2]" in deliveries["3"]


# ── Build status (unified) ──


class TestBuildStatus:
    """Tests for build_status function."""

    def test_build_status_has_ready(self, sample_tasks):
        """Returns ready tasks and not stalled when tasks are available."""
        from lib.build_loop import build_status

        result = build_status(sample_tasks)

        assert result["ready_count"] >= 1
        assert result["stalled"] is False
        assert result["stall_info"] is None
        assert result["pending_count"] >= 1

    def test_build_status_stalled(self, sample_tasks_with_blocked):
        """Returns stalled with info when no tasks are ready."""
        from lib.build_loop import build_status

        result = build_status(sample_tasks_with_blocked)

        assert result["ready_count"] == 0
        assert result["stalled"] is True
        assert result["stall_info"] is not None
        assert result["stall_info"]["pending_count"] >= 1
        assert result["pending_count"] >= 1

    def test_build_status_all_complete(self):
        """No pending tasks means not stalled and nothing ready."""
        from lib.build_loop import build_status

        tasks = [
            {"id": "t1", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
        ]

        result = build_status(tasks)

        assert result["ready_count"] == 0
        assert result["stalled"] is False
        assert result["pending_count"] == 0
