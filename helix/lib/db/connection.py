"""SQLite database connection with write locking.

Uses WAL mode for concurrent reads, write_lock for safe writes.

Note: Plan and workspace tables have been removed. Task management is now
handled by Claude Code's native Task system with metadata.
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


def _apply_migrations(db: sqlite3.Connection) -> None:
    """Apply schema migrations for existing databases."""
    # Get existing columns
    cursor = db.execute("PRAGMA table_info(memory)")
    columns = {row[1] for row in cursor.fetchall()}

    # Migration: Add file_patterns column if missing
    if "file_patterns" not in columns:
        try:
            db.execute("ALTER TABLE memory ADD COLUMN file_patterns TEXT")
            db.commit()
        except Exception:
            pass  # Column might already exist

    # Migration: Change helped/failed from INTEGER to REAL
    # (SQLite is flexible, so existing INTEGER values work with REAL)
    # No action needed - SQLite handles this automatically


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
            helped REAL DEFAULT 0,
            failed REAL DEFAULT 0,
            embedding BLOB,
            source TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_used TEXT,
            file_patterns TEXT
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
    """)
    db.commit()

    # Apply migrations for existing databases
    _apply_migrations(db)


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
