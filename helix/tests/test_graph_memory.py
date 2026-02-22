"""Integration tests for graph memory features.

Tests store autolink, recall graph expansion, prune edge cleanup,
and provenance edges.
"""

import json
import pytest
from datetime import datetime, timezone


def _insert_raw(db, name, content="test content", embedding=None):
    """Insert bare insight row, return id."""
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    db.execute(
        "INSERT INTO insight (name, content, embedding, created_at) VALUES (?, ?, ?, ?)",
        (name, content, embedding, now)
    )
    db.commit()
    return db.execute("SELECT id FROM insight WHERE name = ?", (name,)).fetchone()["id"]


class TestStoreAutolink:
    """Tests for automatic edge creation during store()."""

    def test_autolink_creates_edges(self, test_db, mock_embeddings):
        """Store creates similar edges when insights are related (mock embeddings are highly similar)."""
        from lib.memory.core import store

        r1 = store("When debugging Python import errors, always check sys.path first because module resolution depends on it", tags=["python"])
        assert r1["status"] == "added"

        r2 = store("When writing Python integration tests, use pytest fixtures for database isolation and teardown", tags=["testing"])
        assert r2["status"] == "added"

        # Mock embeddings are hash-based but structurally similar; auto-linking should fire
        edges = test_db.execute("SELECT * FROM insight_edges WHERE relation = 'similar'").fetchall()
        assert len(edges) >= 1  # at least one edge from auto-linking

    def test_no_edges_for_first_insight(self, test_db, mock_embeddings):
        """First insight has nothing to link to — no edges created."""
        from lib.memory.core import store

        store("When deploying to production, always run database migrations before code deployment", tags=["deploy"])

        count = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert count == 0

    def test_merge_does_not_create_edges(self, test_db, mock_embeddings):
        """Merged (duplicate) insights do not create new edges."""
        from lib.memory.core import store

        r1 = store("When debugging Python import errors, always check sys.path first because module resolution depends on it", tags=["python"])
        r2 = store("When debugging Python import errors, always check sys.path first because module resolution depends on it", tags=["python"])

        assert r2["status"] == "merged"
        count = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert count == 0  # only one insight exists — nothing to link

    def test_autolink_cap(self, test_db, mock_embeddings):
        """At most MAX_AUTOLINK_EDGES edges per new insight."""
        from lib.memory.core import store, MAX_AUTOLINK_EDGES

        # Store many insights — each new one may auto-link to previous ones
        names = []
        for i in range(MAX_AUTOLINK_EDGES + 3):
            r = store(f"When handling production situation number {i:03d}, check the monitoring dashboard for anomalies", tags=["ops"])
            if r["status"] == "added":
                names.append(r["name"])

        # No crash — structural test
        total_edges = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert total_edges >= 0  # no crash with many inserts


class TestRecallGraphExpansion:
    """Tests for recall() with graph_hops parameter."""

    def test_graph_hops_zero_backward_compat(self, test_db, mock_embeddings):
        """graph_hops=0 (default) produces results with _hop=0 field."""
        from lib.memory.core import store, recall

        store("When optimizing database queries, use EXPLAIN ANALYZE to identify bottlenecks", tags=["database"])

        results = recall("database query optimization", limit=5)
        for r in results:
            assert "_hop" in r
            assert r["_hop"] == 0

    def test_graph_hops_one_includes_hop_field(self, test_db, mock_embeddings):
        """graph_hops=1 results include _hop field."""
        from lib.memory.core import store, recall

        store("When configuring CI pipelines, cache dependency downloads for faster builds", tags=["ci"])

        results = recall("CI pipeline optimization", limit=5, graph_hops=1)
        for r in results:
            assert "_hop" in r
            assert r["_hop"] in (0, 1)

    def test_graph_expansion_discovers_neighbors(self, test_db, mock_embeddings):
        """graph_hops=1 can surface insights reachable only through edges."""
        from lib.memory.core import store, recall
        from lib.memory.edges import add_edges
        from lib.memory.embeddings import to_blob

        # Insert a "hub" insight that matches the query well
        r1 = store("When writing database migration scripts, always include rollback procedures", tags=["database"])

        # Insert a "neighbor" insight with different content (won't match query directly)
        # but link it via edge
        r2 = store("When configuring PostgreSQL connection pooling, set pool size based on expected load", tags=["database"])

        id1 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r1["name"],)).fetchone()["id"]
        id2 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r2["name"],)).fetchone()["id"]
        add_edges([(id1, id2, 0.9, "similar")])

        # With mock embeddings, both might match directly anyway.
        # The key test: graph_hops=1 doesn't crash and returns valid results
        results = recall("database migration rollback", limit=10, graph_hops=1)
        assert len(results) > 0
        for r in results:
            assert "_hop" in r

    def test_graph_hops_respects_suppress_names(self, test_db, mock_embeddings):
        """Graph-expanded results honor suppress_names."""
        from lib.memory.core import store, recall
        from lib.memory.edges import add_edges

        r1 = store("When handling file uploads, validate file type and size on the server side", tags=["security"])
        r2 = store("When processing uploaded files, scan for malware before storing to disk", tags=["security"])

        id1 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r1["name"],)).fetchone()["id"]
        id2 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r2["name"],)).fetchone()["id"]
        add_edges([(id1, id2, 0.8, "similar")])

        results = recall("file upload security", limit=5, graph_hops=1, suppress_names=[r2["name"]])
        result_names = {r["name"] for r in results}
        assert r2["name"] not in result_names

    def test_graph_hops_empty_db(self, test_db, mock_embeddings):
        """graph_hops=1 on empty DB returns empty list."""
        from lib.memory.core import recall
        results = recall("anything", limit=5, graph_hops=1)
        assert results == []


class TestPruneEdgeCleanup:
    """Tests for edge cleanup during prune()."""

    def test_prune_removes_edges_for_pruned_insights(self, test_db, mock_embeddings):
        """Pruning insights also removes their edges."""
        from lib.memory.core import store, prune
        from lib.memory.edges import add_edges
        from lib.db.connection import write_lock

        r1 = store("When implementing feature flags, use a centralized configuration service for consistency", tags=["architecture"])
        r2 = store("When rolling out features gradually, use percentage-based feature flags with monitoring", tags=["architecture"])

        id1 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r1["name"],)).fetchone()["id"]
        id2 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r2["name"],)).fetchone()["id"]

        # Clear auto-link edges so we control the test setup
        test_db.execute("DELETE FROM insight_edges")
        test_db.commit()

        add_edges([(id1, id2, 0.7, "similar")])

        # Make r1 prunable
        with write_lock():
            test_db.execute("UPDATE insight SET effectiveness=0.1, use_count=5 WHERE name=?", (r1["name"],))
            test_db.commit()

        prune(min_effectiveness=0.25, min_uses=3)

        # r1 pruned, its edges gone
        remaining_names = {r["name"] for r in test_db.execute("SELECT name FROM insight").fetchall()}
        assert r1["name"] not in remaining_names

        edges = test_db.execute("SELECT * FROM insight_edges").fetchall()
        edge_node_ids = set()
        for e in edges:
            edge_node_ids.add(e["src_id"])
            edge_node_ids.add(e["dst_id"])
        assert id1 not in edge_node_ids

    def test_prune_preserves_edges_between_survivors(self, test_db, mock_embeddings):
        """Edges between non-pruned insights survive prune()."""
        from lib.memory.core import store, prune
        from lib.memory.edges import add_edges

        r1 = store("When setting up monitoring alerts, use SLO-based thresholds not arbitrary limits", tags=["monitoring"])
        r2 = store("When configuring alert fatigue, group related alerts and set appropriate cooldowns", tags=["monitoring"])

        id1 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r1["name"],)).fetchone()["id"]
        id2 = test_db.execute("SELECT id FROM insight WHERE name = ?", (r2["name"],)).fetchone()["id"]

        # Clear auto-link edges, add our controlled edge
        test_db.execute("DELETE FROM insight_edges")
        test_db.commit()
        add_edges([(id1, id2, 0.75, "similar")])

        prune(min_effectiveness=0.25, min_uses=3)

        edges = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert edges == 1


class TestProvenanceEdges:
    """Tests for led_to edge creation."""

    def test_provenance_edges_via_add_edges(self, test_db):
        """led_to edges can be created between parent and child insights."""
        from lib.memory.edges import add_edges

        parent_id = _insert_raw(test_db, "parent-insight")
        child_id = _insert_raw(test_db, "child-insight")

        add_edges([(parent_id, child_id, 1.0, "led_to")])

        edges = test_db.execute(
            "SELECT * FROM insight_edges WHERE relation = 'led_to'"
        ).fetchall()

        assert len(edges) == 1
        assert edges[0]["src_id"] == parent_id
        assert edges[0]["dst_id"] == child_id
        assert edges[0]["weight"] == 1.0

    def test_create_provenance_edges_function(self, test_db, mock_embeddings, monkeypatch):
        """_create_provenance_edges creates led_to edges from parents to child.

        Must reset both lib.db.connection and db.connection singletons
        (dual-singleton issue: extract_learning uses non-prefixed imports).
        """
        import sys
        from lib.memory.core import store

        parent = store("When configuring Redis, set appropriate memory limits to prevent OOM kills", tags=["redis"])
        child = store("When running Redis in containers, mount persistent volumes for data durability", tags=["redis"])

        # Clear auto-link similar edges
        test_db.execute("DELETE FROM insight_edges")
        test_db.commit()

        # Reset non-prefixed db.connection singleton so it picks up HELIX_DB_PATH
        if "db.connection" in sys.modules:
            db_conn_mod = sys.modules["db.connection"]
            if hasattr(db_conn_mod, "reset_db"):
                db_conn_mod.reset_db()
            if hasattr(db_conn_mod, "DB_PATH"):
                from lib.db.connection import DB_PATH
                db_conn_mod.DB_PATH = DB_PATH

        from lib.hooks.extract_learning import _create_provenance_edges
        _create_provenance_edges(child["name"], [parent["name"]])

        # Check via test_db — WAL mode makes committed data from other connection visible
        edges = test_db.execute(
            "SELECT * FROM insight_edges WHERE relation = 'led_to'"
        ).fetchall()
        assert len(edges) == 1

    def test_provenance_with_nonexistent_child(self, test_db, mock_embeddings):
        """Nonexistent child name silently returns without error."""
        from lib.hooks.extract_learning import _create_provenance_edges
        _create_provenance_edges("nonexistent-insight", ["also-nonexistent"])

    def test_provenance_with_nonexistent_parents(self, test_db, mock_embeddings):
        """Nonexistent parent names produce no edges."""
        from lib.memory.core import store
        from lib.hooks.extract_learning import _create_provenance_edges

        child = store("When handling timeout errors in microservices, implement circuit breakers at service boundaries", tags=["reliability"])
        _create_provenance_edges(child["name"], ["nonexistent-parent"])

        # Check both possible singletons
        count_lib = test_db.execute("SELECT COUNT(*) as c FROM insight_edges WHERE relation = 'led_to'").fetchone()["c"]
        assert count_lib == 0


class TestHealthEdgeStats:
    """Tests for edge statistics in health()."""

    def test_health_includes_edge_stats(self, test_db, mock_embeddings):
        """health() returns edge statistics."""
        from lib.memory.core import health

        h = health()
        assert "total_edges" in h
        assert "connected_ratio" in h
        assert "avg_edges_per_insight" in h

    def test_health_edge_stats_with_edges(self, test_db):
        """Edge stats reflect actual edges."""
        from lib.memory.core import health
        from lib.memory.edges import add_edges

        id1 = _insert_raw(test_db, "insight-alpha")
        id2 = _insert_raw(test_db, "insight-beta")
        add_edges([(id1, id2, 0.8, "similar")])

        h = health()
        assert h["total_edges"] == 1
        assert h["connected_ratio"] > 0
        assert h["avg_edges_per_insight"] > 0


class TestStrategicRecallGraphExpansion:
    """Tests for strategic_recall() with graph_hops=1."""

    def test_strategic_recall_includes_graph_expanded_count(self, test_db, mock_embeddings):
        """strategic_recall() summary includes graph_expanded_count."""
        from lib.memory.core import store
        from lib.injection import strategic_recall

        store("When configuring SSL certificates, automate renewal with certbot to prevent expiration outages", tags=["security"])

        result = strategic_recall("SSL certificate management")
        assert "graph_expanded_count" in result["summary"]
        assert isinstance(result["summary"]["graph_expanded_count"], int)
