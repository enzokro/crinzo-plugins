"""SQLite database connection with write locking.

Uses WAL mode for concurrent reads, write_lock for safe writes.

Schema v5: Unified insight table replaces memory/memory_edge/memory_file_pattern.
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

    # Get existing columns
    cursor = db.execute("PRAGMA table_info(memory)")
    columns = {row[1] for row in cursor.fetchall()}

    # Migration: Add file_patterns column if missing
    if "file_patterns" not in columns:
        try:
            db.execute("ALTER TABLE memory ADD COLUMN file_patterns TEXT")
            db.commit()
        except Exception:
            pass

    # Migration v2: Drop legacy tables, record version
    if current_version < 2:
        try:
            db.execute("DROP TABLE IF EXISTS exploration")
            db.execute("DROP TABLE IF EXISTS plan")
            db.execute("DROP TABLE IF EXISTS workspace")
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (2, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v3: Migrate JSON file_patterns to normalized table
    if current_version < 3:
        try:
            import json as _json
            rows = db.execute("SELECT name, file_patterns FROM memory WHERE file_patterns IS NOT NULL").fetchall()
            for row in rows:
                try:
                    patterns = _json.loads(row[1])
                    for pattern in patterns:
                        db.execute(
                            "INSERT OR IGNORE INTO memory_file_pattern (memory_name, pattern) VALUES (?, ?)",
                            (row[0], pattern)
                        )
                except Exception:
                    pass
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (3, datetime('now'))")
            db.commit()
        except Exception:
            pass

    # Migration v4: Drop redundant file_patterns JSON column
    # SQLite doesn't support DROP COLUMN directly before 3.35.0, so we recreate the table
    if current_version < 4:
        try:
            # Check if column exists
            cursor = db.execute("PRAGMA table_info(memory)")
            has_column = any(row[1] == "file_patterns" for row in cursor.fetchall())
            if has_column:
                db.executescript("""
                    CREATE TABLE memory_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE NOT NULL,
                        type TEXT NOT NULL,
                        trigger TEXT NOT NULL,
                        resolution TEXT NOT NULL,
                        helped REAL DEFAULT 0,
                        failed REAL DEFAULT 0,
                        embedding BLOB,
                        source TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        last_used TEXT
                    );
                    INSERT INTO memory_new SELECT id, name, type, trigger, resolution, helped, failed, embedding, source, created_at, last_used FROM memory;
                    DROP TABLE memory;
                    ALTER TABLE memory_new RENAME TO memory;
                    CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);
                    CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name);
                """)
            db.execute("INSERT OR REPLACE INTO schema_version VALUES (4, datetime('now'))")
            db.commit()
        except Exception:
            pass

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

        -- Unified insight table (v5+)
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

        -- Legacy tables kept for migration (will be dropped in future)
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            type TEXT NOT NULL,
            trigger TEXT NOT NULL,
            resolution TEXT NOT NULL,
            helped REAL DEFAULT 0,
            failed REAL DEFAULT 0,
            embedding BLOB,
            source TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            last_used TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_memory_type ON memory(type);
        CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name);

        -- Memory relationships (graph edges) - legacy
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
        CREATE INDEX IF NOT EXISTS idx_edge_rel ON memory_edge(rel_type);

        -- Normalized file patterns - legacy
        CREATE TABLE IF NOT EXISTS memory_file_pattern (
            memory_name TEXT NOT NULL,
            pattern TEXT NOT NULL,
            PRIMARY KEY (memory_name, pattern),
            FOREIGN KEY (memory_name) REFERENCES memory(name) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_file_pattern ON memory_file_pattern(pattern);
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
