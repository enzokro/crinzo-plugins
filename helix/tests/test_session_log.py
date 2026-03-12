"""Tests for session transcript archive (v13 schema)."""
import hashlib
import sqlite3
import pytest


class TestSessionLogSchema:
    """Test that v13 migration creates session_log and FTS5."""

    def test_session_log_table_exists(self, test_db):
        """session_log table created by init_db."""
        tables = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_log'"
        ).fetchall()
        assert len(tables) == 1

    def test_session_log_fts_exists(self, test_db):
        """session_log_fts virtual table created."""
        tables = test_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='session_log_fts'"
        ).fetchall()
        assert len(tables) == 1

    def test_insert_and_query(self, test_db):
        """Can insert and query session_log entries."""
        test_db.execute(
            "INSERT INTO session_log (agent_id, agent_type, task_id, outcome, summary, transcript_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("agent-1", "builder", "task-1", "delivered", "Built auth module", "abc123", "2026-03-12T00:00:00")
        )
        test_db.commit()
        rows = test_db.execute("SELECT * FROM session_log").fetchall()
        assert len(rows) == 1
        assert rows[0]["agent_type"] == "builder"
        assert rows[0]["outcome"] == "delivered"

    def test_fts_search(self, test_db):
        """FTS5 index on session_log is queryable."""
        test_db.execute(
            "INSERT INTO session_log (agent_id, agent_type, task_id, outcome, summary, transcript_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("agent-1", "builder", "task-1", "delivered", "Implemented OAuth token refresh", "abc123", "2026-03-12T00:00:00")
        )
        test_db.commit()
        matches = test_db.execute(
            "SELECT * FROM session_log_fts WHERE session_log_fts MATCH ?",
            ("OAuth",)
        ).fetchall()
        assert len(matches) == 1

    def test_fts_delete_trigger(self, test_db):
        """FTS5 delete trigger removes entries."""
        test_db.execute(
            "INSERT INTO session_log (agent_id, agent_type, task_id, outcome, summary, transcript_hash, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("agent-1", "builder", "task-1", "delivered", "Built auth module", "abc123", "2026-03-12T00:00:00")
        )
        test_db.commit()
        test_db.execute("DELETE FROM session_log WHERE agent_id = 'agent-1'")
        test_db.commit()
        matches = test_db.execute(
            "SELECT * FROM session_log_fts WHERE session_log_fts MATCH ?",
            ("auth",)
        ).fetchall()
        assert len(matches) == 0
