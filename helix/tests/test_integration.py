"""Integration tests - end-to-end flows.

Tests critical paths that span multiple modules:
- Store -> Recall -> Inject -> Verify -> Feedback cycle
- Context building with real memories
- Orchestration flows
"""

import pytest


class TestFeedbackLoop:
    """Tests for the complete learning feedback loop."""

    def test_store_inject_feedback_cycle(self, test_db, mock_embeddings):
        """Complete cycle: store -> recall -> inject -> verify -> feedback."""
        from lib.memory.core import store, recall, get, feedback
        from lib.context import build_context

        # 1. Store a failure memory
        store_result = store(
            trigger="Test failure when mocking external payment API gateway",
            resolution="Use dependency injection, mock at service boundary",
            type="failure"
        )
        assert store_result["status"] == "added"
        memory_name = store_result["name"]

        # 2. Recall should find it
        recalled = recall("payment API testing mocks", limit=5)
        names = [r["name"] for r in recalled]
        assert memory_name in names

        # 3. Build context includes it
        task_data = {
            "id": "task-test",
            "subject": "001: fix-payment-tests",
            "description": "Fix failing payment API tests",
            "metadata": {"verify": "pytest tests/", "relevant_files": []}
        }
        context = build_context(task_data, memory_limit=5)
        assert memory_name in context["injected"]

        # 4. Simulate verify pass -> feedback
        result = feedback(context["injected"], 0.5)
        assert result["updated"] >= 1

        # 5. Memory effectiveness increased
        mem = get(memory_name)
        assert mem["helped"] == 0.5
        assert mem["effectiveness"] > 0.5

    def test_effectiveness_increases_on_success(self, test_db, mock_embeddings):
        """Verify pass increases effectiveness over multiple uses."""
        from lib.memory.core import store, get, feedback

        result = store(
            trigger="Authentication token expiry handling in middleware layer",
            resolution="Check exp claim, refresh before expiry, handle 401 gracefully",
            type="failure"
        )
        name = result["name"]

        # Initial effectiveness is 0.5 (neutral)
        mem = get(name)
        assert mem["effectiveness"] == 0.5

        # Two successful uses
        feedback([name], 0.5)
        feedback([name], 0.5)

        mem = get(name)
        # helped = 1.0, failed = 0 -> effectiveness = 1.0
        assert mem["helped"] == 1.0
        assert mem["effectiveness"] == 1.0

    def test_effectiveness_decreases_on_failure(self, test_db, mock_embeddings):
        """Verify fail decreases effectiveness for pruning."""
        from lib.memory.core import store, get, feedback

        result = store(
            trigger="Cache invalidation strategy for distributed session store",
            resolution="Use TTL with event-based invalidation, eventual consistency",
            type="failure"
        )
        name = result["name"]

        # Mix of success and failure
        feedback([name], 0.5)   # +0.5 helped
        feedback([name], -0.5)  # +0.5 failed
        feedback([name], -0.5)  # +0.5 failed

        mem = get(name)
        # helped = 0.5, failed = 1.0 -> effectiveness = 0.5 / 1.5 = 0.333
        assert mem["helped"] == 0.5
        assert mem["failed"] == 1.0
        assert mem["effectiveness"] < 0.5


class TestContextInjection:
    """Tests for context building with real memories."""

    def test_context_with_real_memories(self, test_db, mock_embeddings, sample_memories):
        """build_context returns actual memories from store."""
        from lib.context import build_context

        task_data = {
            "id": "task-auth",
            "subject": "001: implement-authentication",
            "description": "Implement user authentication with secure token handling",
            "metadata": {
                "verify": "pytest tests/test_auth.py",
                "relevant_files": ["src/auth/jwt.py"]
            }
        }

        result = build_context(task_data, memory_limit=5)

        # Should have injected some memories from sample_memories
        assert len(result["injected"]) > 0

        # Prompt should be well-formed
        # Note: INJECTED_MEMORIES removed from prompt (tracked in injection-state for feedback)
        assert "TASK_ID: task-auth" in result["prompt"]
        assert "FAILURES_TO_AVOID:" in result["prompt"]

    def test_context_feedback_ranking(self, test_db, mock_embeddings):
        """Higher effectiveness memories rank higher on next recall."""
        from lib.memory.core import store, recall, feedback

        # Store two similar memories
        r1 = store(
            trigger="Database connection pool exhaustion under high load conditions",
            resolution="Increase pool size, add connection timeout, monitor metrics",
            type="failure"
        )
        r2 = store(
            trigger="Database connection leaks when exceptions occur in transaction",
            resolution="Use context manager, ensure cleanup in finally block",
            type="failure"
        )

        # Give r1 positive feedback
        feedback([r1["name"]], 0.5)
        feedback([r1["name"]], 0.5)

        # Give r2 negative feedback
        feedback([r2["name"]], -0.5)

        # Recall should rank r1 higher
        results = recall("database connection issues", limit=5)
        names = [r["name"] for r in results]

        if r1["name"] in names and r2["name"] in names:
            # r1 should appear before r2
            assert names.index(r1["name"]) < names.index(r2["name"])


class TestOrchestrationFlow:
    """Tests for task graph orchestration."""

    def test_tasks_progress_through_dag(self):
        """Tasks become ready as blockers complete."""
        from lib.dag_utils import get_ready_tasks

        # Initial state: only t1 ready
        tasks = [
            {"id": "t1", "status": "pending", "blockedBy": [], "metadata": {}},
            {"id": "t2", "status": "pending", "blockedBy": ["t1"], "metadata": {}},
            {"id": "t3", "status": "pending", "blockedBy": ["t2"], "metadata": {}},
        ]

        ready = get_ready_tasks(tasks)
        assert ready == ["t1"]

        # After t1 delivers
        tasks[0]["status"] = "completed"
        tasks[0]["metadata"]["helix_outcome"] = "delivered"

        ready = get_ready_tasks(tasks)
        assert ready == ["t2"]

        # After t2 delivers
        tasks[1]["status"] = "completed"
        tasks[1]["metadata"]["helix_outcome"] = "delivered"

        ready = get_ready_tasks(tasks)
        assert ready == ["t3"]

    def test_stall_detection_with_blocked(self):
        """Stall detected when blocker is blocked."""
        from lib.dag_utils import check_stalled

        tasks = [
            {"id": "t1", "status": "completed", "blockedBy": [], "metadata": {"helix_outcome": "delivered"}},
            {"id": "t2", "status": "completed", "blockedBy": ["t1"], "metadata": {"helix_outcome": "blocked"}},
            {"id": "t3", "status": "pending", "blockedBy": ["t2"], "metadata": {}},
        ]

        is_stalled, info = check_stalled(tasks)

        assert is_stalled is True
        assert "t3" in str(info["blocked_by_blocked"])


class TestSystemicMemories:
    """Tests for systemic memory type (replaces OrchestratorMeta)."""

    def test_systemic_memory_stored_and_recalled(self, test_db, mock_embeddings):
        """Systemic type memories can be stored and recalled."""
        from lib.memory.core import store, recall

        # Store systemic memory (what orchestrator does on 3x same failure)
        result = store(
            trigger="Repeated: Import errors in authentication module",
            resolution="UNRESOLVED",
            type="systemic"
        )
        assert result["status"] == "added"

        # Recall should find it
        results = recall("import errors authentication", limit=5)
        names = [r["name"] for r in results]
        types = [r["type"] for r in results]

        assert result["name"] in names
        assert "systemic" in types

    def test_warning_passed_to_context(self, test_db, mock_embeddings):
        """Warning string injected into context appears in prompt."""
        from lib.context import build_context

        task_data = {
            "id": "t4",
            "subject": "004: fix-imports",
            "description": "Fix import structure",
            "metadata": {"verify": "pytest"}
        }

        warning = "Systemic issue detected: import_error (seen 3x). Address this first."
        context = build_context(task_data, warning=warning)

        # Warning should appear in prompt
        assert "WARNING:" in context["prompt"]
        assert "import_error" in context["prompt"]
