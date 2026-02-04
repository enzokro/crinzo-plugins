"""Integration tests - end-to-end flows.

Tests critical paths that span multiple modules:
- Store -> Recall -> Feedback cycle
- Context injection with real insights
- Orchestration flows
"""

import pytest


class TestFeedbackLoop:
    """Tests for the complete learning feedback loop."""

    def test_store_recall_feedback_cycle(self, test_db, mock_embeddings):
        """Complete cycle: store -> recall -> feedback."""
        from lib.memory.core import store, recall, get, feedback

        # 1. Store an insight
        store_result = store(
            content="When testing payment API, use dependency injection and mock at service boundary because it improves isolation",
            tags=["testing", "mocking"]
        )
        assert store_result["status"] == "added"
        insight_name = store_result["name"]

        # 2. Recall should find it
        recalled = recall("payment API testing mocks", limit=5)
        names = [r["name"] for r in recalled]
        assert insight_name in names

        # 3. Simulate verify pass -> feedback
        result = feedback([insight_name], "delivered")
        assert result["updated"] >= 1

        # 4. Insight effectiveness increased
        insight = get(insight_name)
        assert insight["effectiveness"] > 0.5

    def test_effectiveness_increases_on_success(self, test_db, mock_embeddings):
        """Delivered outcome increases effectiveness over multiple uses."""
        from lib.memory.core import store, get, feedback

        result = store(
            content="When handling auth token expiry, check exp claim and refresh before expiry to handle gracefully"
        )
        name = result["name"]

        # Initial effectiveness is 0.5 (neutral)
        insight = get(name)
        assert insight["effectiveness"] == 0.5

        # Two successful uses
        feedback([name], "delivered")
        feedback([name], "delivered")

        insight = get(name)
        # EMA: 0.5 -> 0.55 -> 0.595
        assert insight["effectiveness"] > 0.5

    def test_effectiveness_decreases_on_failure(self, test_db, mock_embeddings):
        """Blocked outcome decreases effectiveness."""
        from lib.memory.core import store, get, feedback

        result = store(
            content="When caching sessions, use TTL with event-based invalidation for eventual consistency"
        )
        name = result["name"]

        # Mix of success and failure
        feedback([name], "delivered")
        feedback([name], "blocked")
        feedback([name], "blocked")

        insight = get(name)
        # EMA after delivered, blocked, blocked should be < 0.5
        assert insight["effectiveness"] < 0.5


class TestContextInjection:
    """Tests for context building with real insights."""

    def test_inject_context_with_real_insights(self, test_db, mock_embeddings, sample_insights):
        """inject_context returns actual insights from store."""
        from lib.injection import inject_context

        result = inject_context("user authentication with secure token handling", limit=5)

        # Should have found some relevant insights
        assert len(result["names"]) > 0
        assert len(result["insights"]) > 0

    def test_context_feedback_ranking(self, test_db, mock_embeddings):
        """Higher effectiveness insights rank higher on next recall."""
        from lib.memory.core import store, recall, feedback

        # Store two similar insights
        r1 = store(
            content="When database connections exhaust under load, increase pool size and add connection timeout"
        )
        r2 = store(
            content="When database connections leak during exceptions, use context manager and ensure cleanup in finally"
        )

        # Give r1 positive feedback
        feedback([r1["name"]], "delivered")
        feedback([r1["name"]], "delivered")

        # Give r2 negative feedback
        feedback([r2["name"]], "blocked")

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
