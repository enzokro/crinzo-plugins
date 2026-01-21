"""SQLite database connection with write locking.

Uses WAL mode for concurrent reads, write_lock for safe writes.
"""

import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

# Thread-safe singleton
_db = None
_db_lock = threading.Lock()
_write_lock = threading.RLock()

# Default database path
DB_PATH = os.environ.get("HELIX_DB_PATH", ".helix/helix.db")


def _resolve_db_path() -> Path:
    """Resolve database path, creating directory if needed."""
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_db() -> sqlite3.Connection:
    """Get database connection (singleton, thread-safe)."""
    global _db

    if _db is not None:
        return _db

    with _db_lock:
        if _db is not None:
            return _db

        db_path = _resolve_db_path()
        _db = sqlite3.connect(str(db_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row

        # Enable WAL mode and foreign keys
        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA foreign_keys=ON")

        # Initialize schema
        init_db(_db)

        return _db


def init_db(db: sqlite3.Connection = None) -> None:
    """Initialize database schema."""
    if db is None:
        db = get_db()

    db.executescript("""
        -- Memories: learned failures and patterns
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL CHECK (type IN ('failure', 'pattern')),
            trigger TEXT NOT NULL,
            resolution TEXT NOT NULL,
            helped INTEGER DEFAULT 0,
            failed INTEGER DEFAULT 0,
            embedding BLOB,
            source TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_used TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);
        CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name);

        -- Memory relationships (graph edges)
        CREATE TABLE IF NOT EXISTS memory_edge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_name TEXT NOT NULL,
            to_name TEXT NOT NULL,
            rel_type TEXT NOT NULL,
            weight REAL DEFAULT 1.0,
            created_at TEXT NOT NULL,
            UNIQUE(from_name, to_name, rel_type)
        );

        CREATE INDEX IF NOT EXISTS idx_edge_from ON memory_edge(from_name);
        CREATE INDEX IF NOT EXISTS idx_edge_to ON memory_edge(to_name);

        -- Explorations: gathered context
        CREATE TABLE IF NOT EXISTS exploration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective TEXT NOT NULL,
            data TEXT NOT NULL,  -- JSON blob
            created_at TEXT NOT NULL
        );

        -- Plans: task decompositions
        CREATE TABLE IF NOT EXISTS plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective TEXT NOT NULL,
            framework TEXT,
            idioms TEXT,  -- JSON
            tasks TEXT NOT NULL,  -- JSON array
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_plan_status ON plan(status);

        -- Workspaces: task execution contexts
        CREATE TABLE IF NOT EXISTS workspace (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER,
            task_seq TEXT NOT NULL,
            task_slug TEXT NOT NULL,
            objective TEXT NOT NULL,
            data TEXT NOT NULL,  -- JSON blob
            status TEXT DEFAULT 'active',
            delivered TEXT DEFAULT '',
            utilized TEXT DEFAULT '[]',  -- JSON array
            created_at TEXT NOT NULL,
            FOREIGN KEY (plan_id) REFERENCES plan(id)
        );

        CREATE INDEX IF NOT EXISTS idx_workspace_status ON workspace(status);
    """)
    db.commit()


@contextmanager
def write_lock():
    """Context manager for write operations."""
    _write_lock.acquire()
    try:
        yield
    finally:
        _write_lock.release()


def reset_db() -> None:
    """Reset database connection (for testing)."""
    global _db
    if _db is not None:
        _db.close()
        _db = None
