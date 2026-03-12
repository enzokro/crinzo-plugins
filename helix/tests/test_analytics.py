"""Tests for graph topology analytics."""
import pytest


def _insert_insight(db, name, content="test content"):
    """Insert a minimal insight row for graph testing."""
    db.execute(
        "INSERT INTO insight (name, content, effectiveness, use_count, causal_hits, created_at, tags) "
        "VALUES (?, ?, 0.5, 0, 0, '2026-01-01T00:00:00', '[]')",
        (name, content)
    )
    db.commit()
    return db.execute("SELECT id FROM insight WHERE name=?", (name,)).fetchone()["id"]


def _add_edge(db, src_id, dst_id, weight=0.7, relation="similar"):
    """Insert an edge directly."""
    db.execute(
        "INSERT OR IGNORE INTO insight_edges (src_id, dst_id, weight, relation, created_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00')",
        (min(src_id, dst_id) if relation == "similar" else src_id,
         max(src_id, dst_id) if relation == "similar" else dst_id,
         weight, relation)
    )
    db.commit()


class TestGraphTooSmall:
    def test_small_graph_returns_flag(self, test_db):
        from lib.memory.analytics import graph_analytics
        # Insert 5 insights (below GRAPH_MIN_SIZE=10)
        ids = [_insert_insight(test_db, f"small-{i}") for i in range(5)]
        _add_edge(test_db, ids[0], ids[1])
        result = graph_analytics(ids)
        assert result["graph_too_small"] is True
        assert result["node_count"] == 5

    def test_empty_graph(self, test_db):
        from lib.memory.analytics import graph_analytics
        result = graph_analytics([])
        assert result["graph_too_small"] is True


class TestConnectedComponents:
    def test_two_disconnected_clusters(self, test_db):
        from lib.memory.analytics import graph_analytics
        ids = [_insert_insight(test_db, f"cluster-{i}") for i in range(12)]
        # Cluster A: 0-5 fully connected
        for i in range(6):
            for j in range(i+1, 6):
                _add_edge(test_db, ids[i], ids[j])
        # Cluster B: 6-11 fully connected
        for i in range(6, 12):
            for j in range(i+1, 12):
                _add_edge(test_db, ids[i], ids[j])
        # No edges between clusters
        result = graph_analytics(ids)
        assert result["graph_too_small"] is False
        assert result["clusters"] == 2
        assert result["largest_cluster"] == 6

    def test_single_connected_component(self, test_db):
        from lib.memory.analytics import graph_analytics
        ids = [_insert_insight(test_db, f"single-{i}") for i in range(10)]
        # Chain: 0-1-2-...-9
        for i in range(9):
            _add_edge(test_db, ids[i], ids[i+1])
        result = graph_analytics(ids)
        assert result["clusters"] == 1
        assert result["largest_cluster"] == 10


class TestArticulationPoints:
    def test_bridge_detected(self, test_db):
        from lib.memory.analytics import graph_analytics
        ids = [_insert_insight(test_db, f"bridge-{i}") for i in range(11)]
        # Cluster A: 0-4 fully connected
        for i in range(5):
            for j in range(i+1, 5):
                _add_edge(test_db, ids[i], ids[j])
        # Cluster B: 6-10 fully connected
        for i in range(6, 11):
            for j in range(i+1, 11):
                _add_edge(test_db, ids[i], ids[j])
        # Bridge: node 5 connects both clusters
        _add_edge(test_db, ids[4], ids[5])
        _add_edge(test_db, ids[5], ids[6])
        result = graph_analytics(ids)
        assert "bridge-5" in result["bridges"]


class TestIsolatesAndDensity:
    def test_isolate_detection(self, test_db):
        from lib.memory.analytics import graph_analytics
        ids = [_insert_insight(test_db, f"iso-{i}") for i in range(10)]
        # Connect only first 8
        for i in range(7):
            _add_edge(test_db, ids[i], ids[i+1])
        # ids[8] and ids[9] are isolates
        result = graph_analytics(ids)
        isolate_names = set(result["isolates"])
        assert "iso-8" in isolate_names
        assert "iso-9" in isolate_names

    def test_density_complete_graph(self, test_db):
        from lib.memory.analytics import graph_analytics
        ids = [_insert_insight(test_db, f"dense-{i}") for i in range(10)]
        # K10: all pairs connected
        for i in range(10):
            for j in range(i+1, 10):
                _add_edge(test_db, ids[i], ids[j])
        result = graph_analytics(ids)
        assert abs(result["density"] - 1.0) < 0.01
