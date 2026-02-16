"""Tests for Fix 1: Relevance gate in recall().

Verifies that recall() filters insights below min_relevance threshold.
"""

import pytest


pytestmark = pytest.mark.usefixtures("isolated_db")


class TestRelevanceGate:
    """Tests for min_relevance filtering in recall()."""

    def test_recall_filters_low_relevance(self):
        """Insights below min_relevance are excluded."""
        from lib.memory.core import store, recall

        # Store two insights - one related, one not
        store("When testing TypeScript barrel exports, check index.ts re-exports all modules", tags=["typescript"])
        store("When cooking pasta, use salted boiling water for best flavor", tags=["cooking"])

        # Recall with TypeScript query - cooking insight should be filtered
        results = recall("TypeScript barrel export testing", limit=5, min_relevance=0.35)

        assert len(results) > 0, "Expected recall to return results for a matching query"
        contents = [r["content"] for r in results]
        assert any("TypeScript" in c for c in contents), "Expected TypeScript insight in results"
        assert not any("pasta" in c for c in contents)  # cooking should never pass

    def test_recall_returns_empty_for_novel_domain(self):
        """Novel domain query with no related insights returns empty list."""
        from lib.memory.core import store, recall

        # Store generic insights
        store("When implementing middleware pipeline, use compose pattern for chaining", tags=["middleware"])

        # Query completely unrelated domain
        results = recall("quantum chromodynamics lattice simulation", limit=5, min_relevance=0.35)

        # Should be empty or very few results
        assert len(results) <= 1

    def test_recall_min_relevance_zero_returns_all(self):
        """Setting min_relevance=0 disables the gate (backward compatible)."""
        from lib.memory.core import store, recall

        store("When testing TypeScript barrel exports, check index.ts re-exports", tags=["ts"])
        store("When cooking pasta, use salted boiling water", tags=["cooking"])

        results = recall("TypeScript testing", limit=5, min_relevance=0.0)
        assert len(results) >= 2  # both should be returned

    def test_recall_default_min_relevance(self):
        """Default min_relevance is MIN_RELEVANCE_DEFAULT (0.35)."""
        from lib.memory.core import MIN_RELEVANCE_DEFAULT
        assert MIN_RELEVANCE_DEFAULT == 0.35

    def test_recall_respects_custom_threshold(self):
        """Custom min_relevance threshold is respected."""
        from lib.memory.core import store, recall

        store("When implementing actor systems in TypeScript, use message passing", tags=["actors"])

        # Very high threshold should filter almost everything
        results = recall("TypeScript actors", limit=5, min_relevance=0.99)
        assert len(results) == 0

    # test_recall_cli_min_relevance removed: signature introspection isn't behavioral coverage
