"""Database connection management.

Simple SQLite with WAL mode for concurrent access.
Single table design - memories are the only persistent state.
"""

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

# Module-level connection (singleton pattern)
_connection: Optional[sqlite3.Connection] = None
_lock = threading.RLock()

# Default paths
DEFAULT_DB_DIR = ".loop"
DEFAULT_DB_NAME = "memory.db"


def _resolve_db_path() -> Path:
    """Resolve database path from environment or default."""
    # Check for explicit override
    if db_path := os.environ.get("LOOP_DB_PATH"):
        return Path(db_path)

    # Use .loop directory in current working directory
    db_dir = Path(DEFAULT_DB_DIR)
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / DEFAULT_DB_NAME


def get_db() -> sqlite3.Connection:
    """Get database connection (creates if needed).

    Uses double-checked locking for thread safety.
    Connection is reused across calls (singleton).
    """
    global _connection

    if _connection is not None:
        return _connection

    with _lock:
        if _connection is not None:
            return _connection

        db_path = _resolve_db_path()
        _connection = sqlite3.connect(
            str(db_path),
            check_same_thread=False,  # we manage thread safety ourselves
            timeout=30.0,
        )

        # Enable WAL mode for better concurrency
        _connection.execute("PRAGMA journal_mode=WAL")
        _connection.execute("PRAGMA foreign_keys=ON")
        _connection.row_factory = sqlite3.Row

        # Initialize schema
        init_db(_connection)

        return _connection


def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Initialize database schema.

    Creates the memory table if it doesn't exist.
    Idempotent - safe to call multiple times.
    """
    if conn is None:
        conn = get_db()

    conn.executescript("""
        -- The memory table: the only persistent state
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

        -- Index for type queries (failures vs patterns)
        CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);

        -- Index for effectiveness queries (helped/failed ratio)
        CREATE INDEX IF NOT EXISTS idx_memory_effectiveness
            ON memory(helped, failed);

        -- Index for name lookups
        CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name);
    """)
    conn.commit()


def reset_db() -> None:
    """Reset database connection (for testing)."""
    global _connection
    with _lock:
        if _connection is not None:
            _connection.close()
            _connection = None


def write_lock():
    """Context manager for write operations."""
    return _lock
