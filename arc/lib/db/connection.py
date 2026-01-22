"""SQLite connection with WAL mode for concurrent access."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

_db = None
_lock = threading.RLock()

DB_PATH = os.environ.get("ARC_DB_PATH", ".arc/arc.db")


def get_db():
    """Get database connection (singleton)."""
    global _db

    if _db is not None:
        return _db

    with _lock:
        if _db is not None:
            return _db

        db_path = Path(DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _db = sqlite3.connect(str(db_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA foreign_keys=ON")

        _init_schema(_db)

        return _db


def _init_schema(db):
    """Initialize database schema."""
    db.executescript("""
        -- Memory: failures and patterns
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('failure', 'pattern')),
            trigger TEXT NOT NULL,
            resolution TEXT NOT NULL,
            embedding BLOB,
            helped INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used TEXT,
            source TEXT
        );

        -- Memory relationships
        CREATE TABLE IF NOT EXISTS edge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_name TEXT NOT NULL,
            to_name TEXT NOT NULL,
            rel_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            UNIQUE(from_name, to_name, rel_type)
        );

        -- Tasks (lightweight, for multi-step work)
        CREATE TABLE IF NOT EXISTS task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            seq INTEGER NOT NULL,
            objective TEXT NOT NULL,
            delta TEXT,  -- JSON array
            status TEXT DEFAULT 'pending',
            delivered TEXT,
            injected TEXT,  -- JSON array of memory names
            utilized TEXT,  -- JSON array of memory names
            created_at TEXT NOT NULL,
            completed_at TEXT,
            UNIQUE(session_id, seq)
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);
        CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name);
        CREATE INDEX IF NOT EXISTS idx_task_session ON task(session_id);
        CREATE INDEX IF NOT EXISTS idx_edge_from ON edge(from_name);
    """)
    db.commit()


@contextmanager
def write_lock():
    """Context manager for write operations."""
    with _lock:
        yield


def reset():
    """Reset connection (for testing)."""
    global _db
    if _db:
        _db.close()
        _db = None
