"""Tests for orchestrator.py - DAG utilities.

Tests cycle detection, task readiness, and stall detection.
"""

import pytest


class TestCycleDetection:
    """Tests for detect_cycles function."""

    def test_detect_no_cycles(self):
        """Valid DAG has no cycles."""
        from lib.orchestrator import detect_cycles

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
        from lib.orchestrator import detect_cycles

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
        from lib.orchestrator import detect_cycles

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
        from lib.orchestrator import detect_cycles

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
        from lib.orchestrator import detect_cycles

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


class TestTaskReadiness:
    """Tests for get_ready_tasks function."""

    def test_get_ready_no_blockers(self, sample_tasks):
        """Pending task with no blockers is ready."""
        from lib.orchestrator import get_ready_tasks

        # Modify sample_tasks: task-003 depends on task-002 which is delivered
        tasks = sample_tasks

        ready = get_ready_tasks(tasks)

        # task-003 should be ready (task-002 delivered)
        assert "task-003" in ready

    def test_get_ready_all_delivered(self):
        """Task is ready when all blockers delivered."""
        from lib.orchestrator import get_ready_tasks

        tasks = [
            {"id": "t1", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
            {"id": "t2", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
            {"id": "t3", "status": "pending", "blockedBy": ["t1", "t2"], "metadata": {}},
        ]

        ready = get_ready_tasks(tasks)

        assert "t3" in ready

    def test_get_ready_blocker_blocked(self, sample_tasks_with_blocked):
        """Task is not ready if blocker was blocked."""
        from lib.orchestrator import get_ready_tasks

        ready = get_ready_tasks(sample_tasks_with_blocked)

        # task-003 depends on task-002 which is blocked
        assert "task-003" not in ready


class TestStallDetection:
    """Tests for check_stalled function."""

    def test_check_stalled_has_ready(self, sample_tasks):
        """Not stalled when ready tasks exist."""
        from lib.orchestrator import check_stalled

        is_stalled, info = check_stalled(sample_tasks)

        assert is_stalled is False
        assert info is None

    def test_check_stalled_all_blocked(self, sample_tasks_with_blocked):
        """Stalled when pending tasks exist but none ready."""
        from lib.orchestrator import check_stalled

        is_stalled, info = check_stalled(sample_tasks_with_blocked)

        assert is_stalled is True
        assert info is not None
        assert info["pending_count"] >= 1
        assert len(info["blocked_by_blocked"]) >= 1

        # Should identify which task is blocked by blocked tasks
        blocked_info = info["blocked_by_blocked"][0]
        assert "task_id" in blocked_info
        assert "blocked_by" in blocked_info
