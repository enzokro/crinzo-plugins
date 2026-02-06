"""Tests for Fix 4: Cross-wave warning synthesis.

Verifies:
- synthesize_wave_warnings() detects convergent issues
- collect_parent_deliveries() maps blockers to delivery summaries
- Union-find clustering works correctly
"""

import pytest
from unittest.mock import patch


class TestUnionFindClusters:
    """Tests for _union_find_clusters."""

    def test_no_clusters_below_threshold(self):
        """Items with low similarity form no clusters."""
        from lib.wave_synthesis import _union_find_clusters

        items = [1, 100, 200]  # arbitrary
        clusters = _union_find_clusters(items, lambda a, b: 0.0, threshold=0.5)
        # Each item is its own cluster
        assert all(len(c) == 1 for c in clusters)

    def test_all_similar_form_one_cluster(self):
        """Items all similar form one cluster."""
        from lib.wave_synthesis import _union_find_clusters

        items = ["a", "b", "c"]
        clusters = _union_find_clusters(items, lambda a, b: 1.0, threshold=0.5)
        assert len(clusters) == 1
        assert len(clusters[0]) == 3

    def test_two_clusters(self):
        """Two groups of similar items form two clusters."""
        from lib.wave_synthesis import _union_find_clusters

        items = [0, 1, 10, 11]

        def sim(a, b):
            return 0.9 if abs(a - b) <= 1 else 0.1

        clusters = _union_find_clusters(items, sim, threshold=0.5)
        assert len(clusters) == 2
        cluster_sizes = sorted(len(c) for c in clusters)
        assert cluster_sizes == [2, 2]


class TestSynthesizeWaveWarnings:
    """Tests for synthesize_wave_warnings."""

    def test_no_warnings_for_single_result(self):
        """Single result cannot form convergent cluster."""
        from lib.wave_synthesis import synthesize_wave_warnings

        results = [{"task_id": "001", "summary": "Fixed barrel exports"}]
        warnings = synthesize_wave_warnings(results)
        assert warnings == []

    def test_no_warnings_for_dissimilar_results(self):
        """Dissimilar results produce no warnings."""
        from lib.wave_synthesis import synthesize_wave_warnings

        results = [
            {"task_id": "001", "summary": "Implemented priority mailbox with actor message queuing"},
            {"task_id": "002", "summary": "Added CSS grid layout for dashboard responsive design"},
        ]
        warnings = synthesize_wave_warnings(results)
        assert warnings == []

    def test_convergent_issues_produce_warning(self):
        """Similar summaries from different tasks produce convergent warning."""
        from lib.wave_synthesis import synthesize_wave_warnings

        results = [
            {"task_id": "009", "summary": "Fixed TS2308 barrel-export error in index.ts by adding re-export"},
            {"task_id": "010", "summary": "Resolved barrel export TS2308 error: missing re-export in index.ts"},
            {"task_id": "012", "summary": "Fixed TS2308: barrel file index.ts needed explicit re-export statement"},
        ]
        warnings = synthesize_wave_warnings(results, threshold=0.5, min_count=2)

        # Should detect convergence among the TS2308 barrel export fixes
        assert len(warnings) >= 1
        assert "CONVERGENT ISSUE" in warnings[0]

    def test_min_count_respected(self):
        """Clusters smaller than min_count don't produce warnings."""
        from lib.wave_synthesis import synthesize_wave_warnings

        results = [
            {"task_id": "001", "summary": "Fixed barrel export error"},
            {"task_id": "002", "summary": "Fixed barrel export issue"},
        ]
        # Require at least 3 convergent results
        warnings = synthesize_wave_warnings(results, min_count=3)
        assert warnings == []

    def test_insight_field_included_in_synthesis(self):
        """Insight content is included in convergence detection."""
        from lib.wave_synthesis import synthesize_wave_warnings

        results = [
            {"task_id": "001", "summary": "Done", "insight": "Barrel exports in TypeScript need explicit re-export"},
            {"task_id": "002", "summary": "Done", "insight": "TypeScript barrel export files require re-export statements"},
        ]
        warnings = synthesize_wave_warnings(results, threshold=0.5, min_count=2)
        # Convergence detected via insight content even though summaries are generic
        assert len(warnings) >= 1


class TestCollectParentDeliveries:
    """Tests for collect_parent_deliveries."""

    def test_maps_deliveries_to_dependent_tasks(self):
        """Correctly maps blocker deliveries to next-wave tasks."""
        from lib.wave_synthesis import collect_parent_deliveries

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
        from lib.wave_synthesis import collect_parent_deliveries

        deliveries = collect_parent_deliveries([], {})
        assert deliveries == {}

    def test_missing_blocker_results_skipped(self):
        """Blockers not in wave results are silently skipped."""
        from lib.wave_synthesis import collect_parent_deliveries

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
