"""SQLite database connection with write locking.

Uses WAL mode for concurrent reads, write_lock for safe writes.

Schema v9: insight table with 256-dim snowflake-arctic-embed-m-v1.5 embeddings.
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


def _get_default_db_path() -> str:
    """Resolve to absolute path, finding .helix in ancestors."""
    env_path = os.environ.get("HELIX_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        helix_dir = parent / ".helix"
        if helix_dir.exists() and helix_dir.is_dir():
            return str(helix_dir / "helix.db")

    return str(cwd / ".helix" / "helix.db")


# Default database path
DB_PATH = _get_default_db_path()


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
    # Check current schema version
    try:
        row = db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] if row and row[0] else 0
    except Exception:
        current_version = 0

    # v1-v4: legacy memory table migrations (removed; tables dropped in v9)

    # Migration v5: Create unified insight table, migrate from memory
    if current_version < 5:
        try:
            # Create insight table
            db.executescript("""
                CREATE TABLE IF NOT EXISTS insight (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    embedding BLOB,
                    effectiveness REAL DEFAULT 0.5,
                    use_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    last_used TEXT,
                    tags TEXT DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_insight_name ON insight(name);
            """)

            # Migrate data from memory table if it exists
            cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory'")
            if cursor.fetchone():
                db.execute("""
                    INSERT OR IGNORE INTO insight (name, content, embedding, effectiveness, use_count, created_at, last_used, tags)
                    SELECT
                        name,
                        trigger || ' -> ' || resolution,
                        embedding,
                        CASE WHEN (helped + failed) > 0 THEN helped / (helped + failed) ELSE 0.5 END,
                        CAST(helped + failed AS INTEGER),
                        created_at,
                        last_used,
                        '["' || type || '"]'
                    FROM memory
                """)

            db.execute("INSERT OR REPLACE INTO schema_version VALUES (5, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v6: Add causal_hits column for causal feedback tracking
    if current_version < 6:
        try:
            db.execute("ALTER TABLE insight ADD COLUMN causal_hits INTEGER DEFAULT 0")
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (6, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v7: Add last_feedback_at for session-level feedback tracking
    if current_version < 7:
        try:
            db.execute("ALTER TABLE insight ADD COLUMN last_feedback_at TEXT")
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (7, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v8: NULL out embedding BLOBs for model migration
    # Old 384-dim MiniLM vectors are incompatible with new 256-dim arctic-embed vectors.
    # Run scripts/reindex.py after upgrade to re-embed all insights.
    if current_version < 8:
        try:
            db.execute("UPDATE insight SET embedding = NULL")
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (8, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v9: Drop zombie tables from pre-v5 schema
    # memory (migrated to insight in v5), memory_edge (orphaned), memory_file_pattern (FK to memory), exploration (dropped in v2 but persists in upgraded DBs)
    if current_version < 9:
        try:
            db.execute("DROP TABLE IF EXISTS memory_file_pattern")
            db.execute("DROP TABLE IF EXISTS memory_edge")
            db.execute("DROP TABLE IF EXISTS memory")
            db.execute("DROP TABLE IF EXISTS exploration")
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (9, datetime('now'))")
            db.commit()
        except Exception:
            pass


def init_db(db: sqlite3.Connection = None) -> None:
    """Initialize database schema."""
    if db is None:
        db = get_db()

    db.executescript("""
        -- Schema versioning
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        -- Unified insight table (v7+)
        CREATE TABLE IF NOT EXISTS insight (
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
