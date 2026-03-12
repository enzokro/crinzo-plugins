"""SQLite database connection with write locking.

Uses WAL mode for concurrent reads, write_lock for safe writes.

Schema v15: insight table + FTS5 hybrid search index + relationship edges + session transcript archive + usage velocity + knowledge generality.
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

        # Enable WAL mode for concurrent reads
        _db.execute("PRAGMA journal_mode=WAL")
        # Allow 5s retry on locked DB (cross-process safety for hook subprocesses)
        _db.execute("PRAGMA busy_timeout = 5000")

        # Initialize schema
        init_db(_db)

        return _db


# v1-v4: legacy memory table migrations (removed; tables dropped in v9)
_MIGRATIONS = [
    # v5: Create unified insight table
    (5, """CREATE TABLE IF NOT EXISTS insight (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            embedding BLOB,
            effectiveness REAL DEFAULT 0.5,
            use_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            last_used TEXT,
            tags TEXT DEFAULT '[]'
        )"""),
    # v6: Add causal_hits column for causal feedback tracking
    (6, "ALTER TABLE insight ADD COLUMN causal_hits INTEGER DEFAULT 0"),
    # v7: Add last_feedback_at for session-level feedback tracking
    (7, "ALTER TABLE insight ADD COLUMN last_feedback_at TEXT"),
    # v8: NULL out embedding BLOBs for model migration
    (8, "UPDATE insight SET embedding = NULL"),
    # v9: Drop zombie tables from pre-v5 schema
    (9, [
        "DROP TABLE IF EXISTS memory_file_pattern",
        "DROP TABLE IF EXISTS memory_edge",
        "DROP TABLE IF EXISTS memory",
        "DROP TABLE IF EXISTS exploration",
    ]),
    # v10: Drop redundant idx_insight_name (UNIQUE constraint already provides autoindex)
    (10, "DROP INDEX IF EXISTS idx_insight_name"),
    # v11: FTS5 full-text search index on insight content + tags
    (11, [
        # External content FTS5 table (no data duplication)
        """CREATE VIRTUAL TABLE IF NOT EXISTS insight_fts
            USING fts5(content, tags, content=insight, content_rowid=id)""",
        # Auto-sync triggers
        """CREATE TRIGGER IF NOT EXISTS insight_fts_ai AFTER INSERT ON insight BEGIN
            INSERT INTO insight_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
        END""",
        """CREATE TRIGGER IF NOT EXISTS insight_fts_ad AFTER DELETE ON insight BEGIN
            INSERT INTO insight_fts(insight_fts, rowid, content, tags) VALUES('delete', old.id, old.content, old.tags);
        END""",
        """CREATE TRIGGER IF NOT EXISTS insight_fts_au AFTER UPDATE OF content, tags ON insight BEGIN
            INSERT INTO insight_fts(insight_fts, rowid, content, tags) VALUES('delete', old.id, old.content, old.tags);
            INSERT INTO insight_fts(rowid, content, tags) VALUES (new.id, new.content, new.tags);
        END""",
        # Index existing insights
        "INSERT INTO insight_fts(insight_fts) VALUES('rebuild')",
    ]),
    # v12: Relationship edges between insights
    (12, [
        """CREATE TABLE IF NOT EXISTS insight_edges (
            src_id INTEGER NOT NULL,
            dst_id INTEGER NOT NULL,
            weight REAL NOT NULL,
            relation TEXT NOT NULL DEFAULT 'similar',
            created_at TEXT NOT NULL,
            PRIMARY KEY (src_id, dst_id, relation)
        )""",
        "CREATE INDEX IF NOT EXISTS idx_edges_src ON insight_edges(src_id)",
        "CREATE INDEX IF NOT EXISTS idx_edges_dst ON insight_edges(dst_id)",
    ]),
    # v13: Session transcript archive for searchable history
    (13, [
        """CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            task_id TEXT,
            outcome TEXT,
            summary TEXT,
            transcript_hash TEXT,
            created_at TEXT NOT NULL
        )""",
        """CREATE VIRTUAL TABLE IF NOT EXISTS session_log_fts
            USING fts5(summary, outcome, content=session_log, content_rowid=id)""",
        """CREATE TRIGGER IF NOT EXISTS session_log_fts_ai AFTER INSERT ON session_log BEGIN
            INSERT INTO session_log_fts(rowid, summary, outcome) VALUES (new.id, new.summary, new.outcome);
        END""",
        """CREATE TRIGGER IF NOT EXISTS session_log_fts_ad AFTER DELETE ON session_log BEGIN
            INSERT INTO session_log_fts(session_log_fts, rowid, summary, outcome) VALUES('delete', old.id, old.summary, old.outcome);
        END""",
    ]),
    # v14: Usage velocity tracking
    (14, "ALTER TABLE insight ADD COLUMN recent_uses INTEGER DEFAULT 0"),
    # v15: Knowledge generality tracking
    (15, [
        "ALTER TABLE insight ADD COLUMN context_spread REAL DEFAULT NULL",
        "ALTER TABLE insight ADD COLUMN context_centroid BLOB DEFAULT NULL",
    ]),
]


def _apply_migrations(db: sqlite3.Connection) -> None:
    """Apply schema migrations for existing databases."""
    try:
        row = db.execute("SELECT MAX(version) FROM schema_version").fetchone()
        current_version = row[0] if row and row[0] else 0
    except Exception:
        current_version = 0

    for version, sql in _MIGRATIONS:
        if current_version >= version:
            continue
        try:
            stmts = [sql] if isinstance(sql, str) else sql
            for s in stmts:
                db.execute(s)
            db.execute(
                "INSERT OR REPLACE INTO schema_version VALUES (?, datetime('now'))",
                (version,),
            )
            db.commit()
        except sqlite3.OperationalError:
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

        -- Unified insight table (v9)
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
            recent_uses INTEGER DEFAULT 0,
            context_spread REAL DEFAULT NULL,
            context_centroid BLOB DEFAULT NULL,
            tags TEXT DEFAULT '[]'
        );

        -- Relationship edges between insights (v12)
        CREATE TABLE IF NOT EXISTS insight_edges (
            src_id INTEGER NOT NULL,
            dst_id INTEGER NOT NULL,
            weight REAL NOT NULL,
            relation TEXT NOT NULL DEFAULT 'similar',
            created_at TEXT NOT NULL,
            PRIMARY KEY (src_id, dst_id, relation)
        );
        CREATE INDEX IF NOT EXISTS idx_edges_src ON insight_edges(src_id);
        CREATE INDEX IF NOT EXISTS idx_edges_dst ON insight_edges(dst_id);

        -- Session transcript archive (v13)
        CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            task_id TEXT,
            outcome TEXT,
            summary TEXT,
            transcript_hash TEXT,
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
