"""Tests for graph edge helpers (lib/memory/edges.py).

Uses raw DB inserts to isolate edge helper behavior from store() auto-linking.
"""

import pytest


def _insert_insight(db, name, content="test content"):
    """Insert a bare insight row (no embedding, no auto-linking)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    db.execute(
        "INSERT INTO insight (name, content, created_at) VALUES (?, ?, ?)",
        (name, content, now)
    )
    db.commit()
    return db.execute("SELECT id FROM insight WHERE name = ?", (name,)).fetchone()["id"]


class TestAddEdges:
    """Tests for add_edges()."""

    def test_similar_canonical_ordering(self, test_db):
        """Similar edges enforce canonical order (min, max)."""
        from lib.memory.edges import add_edges

        id1 = _insert_insight(test_db, "insight-a")
        id2 = _insert_insight(test_db, "insight-b")

        # Insert (id2, id1) — should be stored as (min, max)
        add_edges([(id2, id1, 0.75, "similar")])

        edge = test_db.execute("SELECT * FROM insight_edges").fetchone()
        assert edge is not None
        assert edge["src_id"] == min(id1, id2)
        assert edge["dst_id"] == max(id1, id2)
        assert edge["relation"] == "similar"
        assert edge["weight"] == 0.75

    def test_led_to_directional(self, test_db):
        """led_to edges preserve direction (parent -> child)."""
        from lib.memory.edges import add_edges

        id1 = _insert_insight(test_db, "parent-insight")
        id2 = _insert_insight(test_db, "child-insight")

        add_edges([(id1, id2, 1.0, "led_to")])

        edge = test_db.execute("SELECT * FROM insight_edges").fetchone()
        assert edge["src_id"] == id1
        assert edge["dst_id"] == id2
        assert edge["relation"] == "led_to"

    def test_no_self_loops(self, test_db):
        """Self-loop edges are rejected."""
        from lib.memory.edges import add_edges

        rid = _insert_insight(test_db, "solo-insight")
        add_edges([(rid, rid, 1.0, "similar")])

        count = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert count == 0

    def test_insert_or_ignore_duplicates(self, test_db):
        """Duplicate edges are silently ignored."""
        from lib.memory.edges import add_edges

        id1 = _insert_insight(test_db, "insight-x")
        id2 = _insert_insight(test_db, "insight-y")

        add_edges([(id1, id2, 0.8, "similar")])
        add_edges([(id1, id2, 0.9, "similar")])  # duplicate PK — ignored

        count = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert count == 1
        # Weight should be from first insert (0.8), not overwritten
        edge = test_db.execute("SELECT weight FROM insight_edges").fetchone()
        assert edge["weight"] == 0.8

    def test_multiple_relations_same_pair(self, test_db):
        """Same pair can have different relation types (PK includes relation)."""
        from lib.memory.edges import add_edges

        id1 = _insert_insight(test_db, "insight-m")
        id2 = _insert_insight(test_db, "insight-n")

        add_edges([(id1, id2, 0.7, "similar"), (id1, id2, 1.0, "led_to")])

        count = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert count == 2

    def test_empty_input(self, test_db):
        """Empty edge list returns 0."""
        from lib.memory.edges import add_edges
        assert add_edges([]) == 0


class TestGetNeighbors:
    """Tests for get_neighbors()."""

    def test_bidirectional_lookup(self, test_db):
        """Finds neighbors regardless of edge direction."""
        from lib.memory.edges import add_edges, get_neighbors

        id1 = _insert_insight(test_db, "center")
        id2 = _insert_insight(test_db, "left")
        id3 = _insert_insight(test_db, "right")

        # id1-id2 via similar (canonical), id3->id1 via led_to (directional)
        add_edges([(id1, id2, 0.7, "similar"), (id3, id1, 0.6, "led_to")])

        neighbors = get_neighbors([id1])
        neighbor_ids = {n["id"] for n in neighbors}
        assert id2 in neighbor_ids
        assert id3 in neighbor_ids

    def test_relation_filter(self, test_db):
        """Filters neighbors by relation type."""
        from lib.memory.edges import add_edges, get_neighbors

        id1 = _insert_insight(test_db, "hub")
        id2 = _insert_insight(test_db, "similar-node")
        id3 = _insert_insight(test_db, "derived-node")

        add_edges([
            (id1, id2, 0.7, "similar"),
            (id1, id3, 1.0, "led_to"),
        ])

        similar_only = get_neighbors([id1], relation="similar")
        led_to_only = get_neighbors([id1], relation="led_to")

        similar_ids = {n["id"] for n in similar_only}
        led_to_ids = {n["id"] for n in led_to_only}

        assert id2 in similar_ids
        assert id3 not in similar_ids
        assert id3 in led_to_ids
        assert id2 not in led_to_ids

    def test_limit(self, test_db):
        """Respects limit parameter."""
        from lib.memory.edges import add_edges, get_neighbors

        id1 = _insert_insight(test_db, "center-node")
        edges = []
        for i in range(5):
            oid = _insert_insight(test_db, f"spoke-{i}")
            edges.append((id1, oid, 0.7 + i * 0.01, "similar"))
        add_edges(edges)

        neighbors = get_neighbors([id1], limit=3)
        assert len(neighbors) == 3

    def test_empty_ids(self, test_db):
        """Empty input returns empty output."""
        from lib.memory.edges import get_neighbors
        assert get_neighbors([]) == []

    def test_excludes_source_ids(self, test_db):
        """Source IDs are excluded from neighbor results."""
        from lib.memory.edges import add_edges, get_neighbors

        id1 = _insert_insight(test_db, "node-a")
        id2 = _insert_insight(test_db, "node-b")

        add_edges([(id1, id2, 0.8, "similar")])

        neighbors = get_neighbors([id1])
        neighbor_ids = {n["id"] for n in neighbors}
        assert id1 not in neighbor_ids
        assert id2 in neighbor_ids


class TestDeleteEdgesFor:
    """Tests for delete_edges_for()."""

    def test_cleans_both_directions(self, test_db):
        """Deletes edges where target appears as src or dst."""
        from lib.memory.edges import add_edges, delete_edges_for

        id1 = _insert_insight(test_db, "node-1")
        id2 = _insert_insight(test_db, "node-2")
        id3 = _insert_insight(test_db, "node-3")

        add_edges([
            (id1, id2, 0.7, "similar"),
            (id2, id3, 0.8, "similar"),
            (id1, id3, 0.6, "similar"),
        ])

        # Delete edges for id2 — removes (id1,id2) and (id2,id3), keeps (id1,id3)
        deleted = delete_edges_for([id2])
        assert deleted == 2

        remaining = test_db.execute("SELECT COUNT(*) as c FROM insight_edges").fetchone()["c"]
        assert remaining == 1

    def test_empty_ids(self, test_db):
        """Empty input returns 0."""
        from lib.memory.edges import delete_edges_for
        assert delete_edges_for([]) == 0


class TestSchemaV12Migration:
    """Test v12 migration creates insight_edges table on existing DB."""

    def test_migration_creates_table(self, tmp_path, monkeypatch):
        """v12 migration adds insight_edges table to existing v11 DB."""
        import sqlite3
        from lib.db import connection

        db_path = str(tmp_path / "migration_test.db")
        monkeypatch.setenv("HELIX_DB_PATH", db_path)
        connection.DB_PATH = db_path
        connection.reset_db()

        # Create a v11 DB manually
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        db.executescript("""
            CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
            CREATE TABLE insight (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                effectiveness REAL DEFAULT 0.5,
                use_count INTEGER DEFAULT 0,
                causal_hits INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_used TEXT,
                last_feedback_at TEXT,
                tags TEXT DEFAULT '[]'
            );
            INSERT INTO schema_version VALUES (11, '2024-01-01');
        """)
        db.commit()
        db.close()

        # Now init via connection module — should run v12 migration
        connection.reset_db()
        conn = connection.get_db()

        # Verify table exists
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        assert "insight_edges" in tables

        # Verify schema version updated
        version = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        assert version >= 12

        connection.reset_db()
