"""Database connection management for FTL."""

import os
import threading
from pathlib import Path
from fastsql import database
from sqlalchemy import text

_db = None
_db_init_lock = threading.RLock()
DB_PATH = Path(os.environ.get('FTL_DB_PATH', '.ftl/ftl.db'))


def get_db():
    """Get or create database connection (singleton pattern).

    Returns the fastsql database object, creating it if needed.
    Database file is created at .ftl/ftl.db relative to cwd.

    FK enforcement is enabled on connection to prevent orphaned edges.
    Uses double-checked locking to prevent duplicate connections at startup.
    """
    global _db
    if _db is None:  # Fast path: skip lock if already initialized
        with _db_init_lock:
            if _db is None:  # Re-check inside lock to prevent race
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                _db = database(str(DB_PATH))
                # Enable FK enforcement - SQLite disables by default
                _db.execute(text("PRAGMA foreign_keys=ON"))
    return _db


def init_db():
    """Create all tables and indexes. Idempotent operation.

    Uses fastsql's create() with dataclasses. Tables are created
    with IF NOT EXISTS semantics.
    """
    db = get_db()
    from .schema import (Memory, MemoryEdge, Campaign, Workspace,
                         Archive, Exploration, PhaseState, Event,
                         ExplorerResult, Plan, Benchmark)

    # Create tables (fastsql handles IF NOT EXISTS)
    db.create(Memory, pk='id')
    db.create(MemoryEdge, pk='id')
    db.create(Campaign, pk='id')
    db.create(Workspace, pk='id')
    db.create(Archive, pk='id')
    db.create(Exploration, pk='id')
    db.create(PhaseState, pk='id')
    db.create(Event, pk='id')
    db.create(ExplorerResult, pk='id')
    db.create(Plan, pk='id')
    db.create(Benchmark, pk='id')

    # Create indexes for query performance
    _create_indexes(db)


def _create_indexes(db):
    """Create database indexes for common query patterns."""
    indexes = [
        "CREATE INDEX IF NOT EXISTS idx_memory_type_importance ON memory(type, importance DESC)",
        "CREATE INDEX IF NOT EXISTS idx_memory_name ON memory(name)",
        "CREATE INDEX IF NOT EXISTS idx_memory_name_type ON memory(name, type)",
        "CREATE INDEX IF NOT EXISTS idx_edge_from ON memory_edge(from_id, rel_type)",
        "CREATE INDEX IF NOT EXISTS idx_edge_to ON memory_edge(to_id)",
        "CREATE INDEX IF NOT EXISTS idx_campaign_status ON campaign(status)",
        "CREATE INDEX IF NOT EXISTS idx_workspace_campaign ON workspace(campaign_id)",
        "CREATE INDEX IF NOT EXISTS idx_workspace_status ON workspace(status)",
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_workspace_id ON workspace(workspace_id)",
        "CREATE INDEX IF NOT EXISTS idx_archive_framework ON archive(framework)",
        "CREATE INDEX IF NOT EXISTS idx_event_timestamp ON event(timestamp)",
        "CREATE INDEX IF NOT EXISTS idx_explorer_result_session ON explorer_result(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_plan_status ON plan(status)",
        "CREATE INDEX IF NOT EXISTS idx_plan_campaign ON plan(campaign_id)",
        "CREATE INDEX IF NOT EXISTS idx_benchmark_run ON benchmark(run_id)",
        # Partial unique index: enforce at most one active campaign
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_campaign_singleton_active ON campaign(status) WHERE status = 'active'",
    ]
    for idx_sql in indexes:
        db.execute(text(idx_sql))


def reset_db():
    """Reset database connection and optionally delete file.

    Used primarily for testing to ensure clean state.
    """
    global _db
    if _db is not None:
        _db = None
    if DB_PATH.exists():
        DB_PATH.unlink()


def set_db_path(path: Path):
    """Override database path (for testing).

    Must be called before first get_db() call.
    """
    global DB_PATH, _db
    DB_PATH = path
    _db = None
