#!/usr/bin/env python3
"""Task snapshot and persistence utility for Claude Code native tasks.

Captures the current state of Claude Code's native Task system and persists
to SQLite for analysis, history tracking, and cross-session insights.

Usage:
    # Snapshot current tasks to database
    python3 parse_tasks.py snapshot

    # Snapshot with custom task list ID
    python3 parse_tasks.py snapshot --task-list-id my-project

    # List all snapshots
    python3 parse_tasks.py list

    # Show tasks from a specific snapshot
    python3 parse_tasks.py show --snapshot-id 5

    # Export snapshot to JSON
    python3 parse_tasks.py export --snapshot-id 5

    # Analyze task patterns
    python3 parse_tasks.py analyze

    # Show current tasks (no persistence)
    python3 parse_tasks.py current
"""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import hashlib


# =============================================================================
# Database Schema (matches original helix Plan/Task/Workspace structure)
# =============================================================================

@dataclass
class Task:
    """A single executable unit from Claude Code's native task system.

    Maps to Claude Code TaskCreate/TaskGet structure with helix metadata.
    """
    task_id: str  # Claude Code's native task ID
    subject: str  # "001: slug-name" format
    description: str  # Task objective
    status: str  # pending, in_progress, completed

    # Parsed from subject
    seq: str = ""  # "001", "002", etc.
    slug: str = ""  # Human-readable identifier

    # Dependencies
    blocked_by: List[str] = field(default_factory=list)  # Task IDs
    blocks: List[str] = field(default_factory=list)  # Task IDs

    # Ownership
    owner: Optional[str] = None  # Agent that claimed this task

    # Helix metadata (from task.metadata)
    delta: List[str] = field(default_factory=list)  # Files to modify
    verify: str = ""  # Verification command
    budget: int = 7  # Tool call budget
    framework: Optional[str] = None
    idioms: Dict[str, List[str]] = field(default_factory=dict)

    # Results (populated after completion)
    delivered: str = ""  # What was accomplished
    utilized: List[str] = field(default_factory=list)  # Memories that helped

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # Database ID (auto-generated on persist)
    id: Optional[int] = None

    def __post_init__(self):
        """Parse seq and slug from subject if not provided."""
        if not self.seq and self.subject:
            parts = self.subject.split(":", 1)
            self.seq = parts[0].strip() if parts else ""
            self.slug = parts[1].strip() if len(parts) > 1 else self.subject


@dataclass
class Plan:
    """A collection of tasks representing a decomposed objective.

    Reconstructed from Claude Code's native task list state.
    """
    objective: str
    framework: Optional[str] = None
    idioms: Dict[str, List[str]] = field(default_factory=dict)

    tasks: List[Task] = field(default_factory=list)

    # Task list identification
    task_list_id: Optional[str] = None  # CLAUDE_CODE_TASK_LIST_ID
    session_id: Optional[str] = None

    # Status
    status: str = "active"  # active, complete, stuck

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    # Database ID
    id: Optional[int] = None

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    @property
    def completed_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == "completed")

    @property
    def pending_count(self) -> int:
        return sum(1 for t in self.tasks if t.status == "pending")

    @property
    def blocked_count(self) -> int:
        return sum(1 for t in self.tasks
                   if t.status == "completed" and t.delivered.startswith("BLOCKED:"))

    def ready_tasks(self) -> List[Task]:
        """Get tasks whose dependencies are all complete."""
        completed_ids = {t.task_id for t in self.tasks if t.status == "completed"}
        ready = []
        for t in self.tasks:
            if t.status != "pending":
                continue
            if not t.blocked_by or all(b in completed_ids for b in t.blocked_by):
                ready.append(t)
        return ready


@dataclass
class Snapshot:
    """A point-in-time capture of the task system state."""
    plan: Plan
    captured_at: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = "claude_code"  # Where the snapshot came from
    notes: str = ""

    # Computed hash for deduplication
    content_hash: str = ""

    # Database ID
    id: Optional[int] = None

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute hash of task content for deduplication."""
        content = json.dumps({
            "objective": self.plan.objective,
            "tasks": [
                {
                    "task_id": t.task_id,
                    "subject": t.subject,
                    "status": t.status,
                    "delivered": t.delivered,
                }
                for t in self.plan.tasks
            ]
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# =============================================================================
# Database Connection
# =============================================================================

_db = None
_db_lock = threading.Lock()
_write_lock = threading.RLock()

DB_PATH = os.environ.get(
    "TASK_SNAPSHOT_DB",
    str(Path.home() / ".claude" / "task_snapshots.db")
)


def get_db() -> sqlite3.Connection:
    """Get database connection (singleton, thread-safe)."""
    global _db

    if _db is not None:
        return _db

    with _db_lock:
        if _db is not None:
            return _db

        db_path = Path(DB_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        _db = sqlite3.connect(str(db_path), check_same_thread=False)
        _db.row_factory = sqlite3.Row

        _db.execute("PRAGMA journal_mode=WAL")
        _db.execute("PRAGMA foreign_keys=ON")

        init_db(_db)
        return _db


def init_db(db: sqlite3.Connection) -> None:
    """Initialize database schema."""
    db.executescript("""
        -- Snapshots: point-in-time captures
        CREATE TABLE IF NOT EXISTS snapshot (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content_hash TEXT NOT NULL,
            source TEXT DEFAULT 'claude_code',
            notes TEXT DEFAULT '',
            captured_at TEXT NOT NULL,
            UNIQUE(content_hash)
        );

        CREATE INDEX IF NOT EXISTS idx_snapshot_captured ON snapshot(captured_at);

        -- Plans: reconstructed task decompositions
        CREATE TABLE IF NOT EXISTS plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id INTEGER NOT NULL,
            objective TEXT NOT NULL,
            framework TEXT,
            idioms TEXT,  -- JSON
            task_list_id TEXT,
            session_id TEXT,
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (snapshot_id) REFERENCES snapshot(id)
        );

        CREATE INDEX IF NOT EXISTS idx_plan_snapshot ON plan(snapshot_id);
        CREATE INDEX IF NOT EXISTS idx_plan_status ON plan(status);

        -- Tasks: individual executable units
        CREATE TABLE IF NOT EXISTS task (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            task_id TEXT NOT NULL,  -- Claude Code's ID
            subject TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            seq TEXT,
            slug TEXT,
            blocked_by TEXT,  -- JSON array
            blocks TEXT,  -- JSON array
            owner TEXT,
            delta TEXT,  -- JSON array
            verify TEXT,
            budget INTEGER DEFAULT 7,
            framework TEXT,
            idioms TEXT,  -- JSON
            delivered TEXT DEFAULT '',
            utilized TEXT,  -- JSON array
            created_at TEXT NOT NULL,
            completed_at TEXT,
            FOREIGN KEY (plan_id) REFERENCES plan(id)
        );

        CREATE INDEX IF NOT EXISTS idx_task_plan ON task(plan_id);
        CREATE INDEX IF NOT EXISTS idx_task_status ON task(status);
        CREATE INDEX IF NOT EXISTS idx_task_seq ON task(seq);
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


# =============================================================================
# Claude Code Task Reader
# =============================================================================

def find_task_files() -> List[Path]:
    """Find Claude Code task storage locations."""
    claude_dir = Path.home() / ".claude"
    task_files = []

    # Check for task list files
    tasks_dir = claude_dir / "tasks"
    if tasks_dir.exists():
        for task_list_dir in tasks_dir.iterdir():
            if task_list_dir.is_dir():
                for f in task_list_dir.glob("*.json"):
                    task_files.append(f)

    # Check project session directories
    projects_dir = claude_dir / "projects"
    if projects_dir.exists():
        for project_dir in projects_dir.iterdir():
            if project_dir.is_dir():
                for session_dir in project_dir.iterdir():
                    if session_dir.is_dir():
                        # Look for task state files
                        for f in session_dir.glob("tasks*.json"):
                            task_files.append(f)

    return task_files


def read_task_list_from_env() -> Optional[str]:
    """Read task list ID from environment."""
    return os.environ.get("CLAUDE_CODE_TASK_LIST_ID")


def parse_claude_task(task_data: dict) -> Task:
    """Parse a Claude Code task into our Task dataclass."""
    metadata = task_data.get("metadata", {})

    return Task(
        task_id=task_data.get("id", ""),
        subject=task_data.get("subject", ""),
        description=task_data.get("description", ""),
        status=task_data.get("status", "pending"),
        blocked_by=task_data.get("blockedBy", []),
        blocks=task_data.get("blocks", []),
        owner=task_data.get("owner"),
        delta=metadata.get("delta", []),
        verify=metadata.get("verify", ""),
        budget=metadata.get("budget", 7),
        framework=metadata.get("framework"),
        idioms=metadata.get("idioms", {}),
        delivered=metadata.get("delivered", ""),
        utilized=metadata.get("utilized", []),
        created_at=task_data.get("createdAt", datetime.now().isoformat()),
        completed_at=task_data.get("completedAt"),
    )


def reconstruct_plan_from_tasks(tasks: List[Task], task_list_id: Optional[str] = None) -> Plan:
    """Reconstruct a Plan from a list of tasks."""
    # Try to infer objective from first task or use generic
    objective = "Reconstructed from task snapshot"
    if tasks:
        # Try to find common theme in descriptions
        descriptions = [t.description for t in tasks if t.description]
        if descriptions:
            objective = f"Tasks: {descriptions[0][:100]}..." if len(descriptions[0]) > 100 else descriptions[0]

    # Collect framework/idioms from tasks
    framework = None
    idioms = {}
    for t in tasks:
        if t.framework and not framework:
            framework = t.framework
        if t.idioms:
            for key, vals in t.idioms.items():
                if key not in idioms:
                    idioms[key] = []
                idioms[key].extend(v for v in vals if v not in idioms[key])

    # Determine plan status
    if not tasks:
        status = "empty"
    elif all(t.status == "completed" for t in tasks):
        status = "complete"
    elif any(t.status == "completed" and t.delivered.startswith("BLOCKED:") for t in tasks):
        # Check if blocked tasks are blocking others
        blocked_ids = {t.task_id for t in tasks
                       if t.status == "completed" and t.delivered.startswith("BLOCKED:")}
        pending = [t for t in tasks if t.status == "pending"]
        stuck = any(any(b in blocked_ids for b in t.blocked_by) for t in pending)
        status = "stuck" if stuck else "active"
    else:
        status = "active"

    return Plan(
        objective=objective,
        framework=framework,
        idioms=idioms,
        tasks=tasks,
        task_list_id=task_list_id,
        status=status,
    )


# =============================================================================
# Snapshot Operations
# =============================================================================

def capture_snapshot(
    tasks: List[Task],
    task_list_id: Optional[str] = None,
    notes: str = ""
) -> Snapshot:
    """Create a snapshot from current tasks."""
    plan = reconstruct_plan_from_tasks(tasks, task_list_id)
    return Snapshot(plan=plan, notes=notes)


def save_snapshot(snapshot: Snapshot) -> dict:
    """Persist a snapshot to the database."""
    db = get_db()

    with write_lock():
        # Check for duplicate
        existing = db.execute(
            "SELECT id FROM snapshot WHERE content_hash = ?",
            (snapshot.content_hash,)
        ).fetchone()

        if existing:
            return {
                "status": "duplicate",
                "snapshot_id": existing["id"],
                "message": "Identical snapshot already exists"
            }

        # Insert snapshot
        cursor = db.execute(
            """INSERT INTO snapshot (content_hash, source, notes, captured_at)
               VALUES (?, ?, ?, ?)""",
            (snapshot.content_hash, snapshot.source, snapshot.notes, snapshot.captured_at)
        )
        snapshot_id = cursor.lastrowid

        # Insert plan
        plan = snapshot.plan
        cursor = db.execute(
            """INSERT INTO plan (snapshot_id, objective, framework, idioms,
                                 task_list_id, session_id, status, created_at, completed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot_id,
                plan.objective,
                plan.framework,
                json.dumps(plan.idioms),
                plan.task_list_id,
                plan.session_id,
                plan.status,
                plan.created_at,
                plan.completed_at,
            )
        )
        plan_id = cursor.lastrowid

        # Insert tasks
        for task in plan.tasks:
            db.execute(
                """INSERT INTO task (plan_id, task_id, subject, description, status,
                                     seq, slug, blocked_by, blocks, owner,
                                     delta, verify, budget, framework, idioms,
                                     delivered, utilized, created_at, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    plan_id,
                    task.task_id,
                    task.subject,
                    task.description,
                    task.status,
                    task.seq,
                    task.slug,
                    json.dumps(task.blocked_by),
                    json.dumps(task.blocks),
                    task.owner,
                    json.dumps(task.delta),
                    task.verify,
                    task.budget,
                    task.framework,
                    json.dumps(task.idioms),
                    task.delivered,
                    json.dumps(task.utilized),
                    task.created_at,
                    task.completed_at,
                )
            )

        db.commit()

        return {
            "status": "created",
            "snapshot_id": snapshot_id,
            "plan_id": plan_id,
            "task_count": len(plan.tasks),
            "content_hash": snapshot.content_hash,
        }


def load_snapshot(snapshot_id: int) -> Optional[Snapshot]:
    """Load a snapshot from the database."""
    db = get_db()

    snap_row = db.execute(
        "SELECT * FROM snapshot WHERE id = ?", (snapshot_id,)
    ).fetchone()

    if not snap_row:
        return None

    plan_row = db.execute(
        "SELECT * FROM plan WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()

    if not plan_row:
        return None

    task_rows = db.execute(
        "SELECT * FROM task WHERE plan_id = ? ORDER BY seq", (plan_row["id"],)
    ).fetchall()

    tasks = []
    for row in task_rows:
        tasks.append(Task(
            id=row["id"],
            task_id=row["task_id"],
            subject=row["subject"],
            description=row["description"],
            status=row["status"],
            seq=row["seq"],
            slug=row["slug"],
            blocked_by=json.loads(row["blocked_by"]) if row["blocked_by"] else [],
            blocks=json.loads(row["blocks"]) if row["blocks"] else [],
            owner=row["owner"],
            delta=json.loads(row["delta"]) if row["delta"] else [],
            verify=row["verify"],
            budget=row["budget"],
            framework=row["framework"],
            idioms=json.loads(row["idioms"]) if row["idioms"] else {},
            delivered=row["delivered"],
            utilized=json.loads(row["utilized"]) if row["utilized"] else [],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
        ))

    plan = Plan(
        id=plan_row["id"],
        objective=plan_row["objective"],
        framework=plan_row["framework"],
        idioms=json.loads(plan_row["idioms"]) if plan_row["idioms"] else {},
        tasks=tasks,
        task_list_id=plan_row["task_list_id"],
        session_id=plan_row["session_id"],
        status=plan_row["status"],
        created_at=plan_row["created_at"],
        completed_at=plan_row["completed_at"],
    )

    return Snapshot(
        id=snap_row["id"],
        plan=plan,
        captured_at=snap_row["captured_at"],
        source=snap_row["source"],
        notes=snap_row["notes"],
        content_hash=snap_row["content_hash"],
    )


def list_snapshots(limit: int = 20) -> List[dict]:
    """List recent snapshots."""
    db = get_db()

    rows = db.execute("""
        SELECT s.id, s.captured_at, s.source, s.notes, s.content_hash,
               p.objective, p.status,
               COUNT(t.id) as task_count,
               SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed,
               SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending
        FROM snapshot s
        JOIN plan p ON p.snapshot_id = s.id
        LEFT JOIN task t ON t.plan_id = p.id
        GROUP BY s.id
        ORDER BY s.captured_at DESC
        LIMIT ?
    """, (limit,)).fetchall()

    return [{
        "id": r["id"],
        "captured_at": r["captured_at"],
        "source": r["source"],
        "notes": r["notes"],
        "content_hash": r["content_hash"],
        "objective": r["objective"][:60] + "..." if len(r["objective"]) > 60 else r["objective"],
        "status": r["status"],
        "task_count": r["task_count"],
        "completed": r["completed"],
        "pending": r["pending"],
    } for r in rows]


def analyze_snapshots() -> dict:
    """Analyze patterns across all snapshots."""
    db = get_db()

    # Overall stats
    total_snapshots = db.execute("SELECT COUNT(*) as c FROM snapshot").fetchone()["c"]
    total_tasks = db.execute("SELECT COUNT(*) as c FROM task").fetchone()["c"]

    # Status distribution
    status_dist = db.execute("""
        SELECT status, COUNT(*) as count
        FROM task
        GROUP BY status
    """).fetchall()

    # Block rate
    blocked = db.execute("""
        SELECT COUNT(*) as c FROM task
        WHERE delivered LIKE 'BLOCKED:%'
    """).fetchone()["c"]

    # Average tasks per plan
    avg_tasks = db.execute("""
        SELECT AVG(task_count) as avg FROM (
            SELECT COUNT(*) as task_count FROM task GROUP BY plan_id
        )
    """).fetchone()["avg"] or 0

    # Most common frameworks
    frameworks = db.execute("""
        SELECT framework, COUNT(*) as count
        FROM plan
        WHERE framework IS NOT NULL
        GROUP BY framework
        ORDER BY count DESC
        LIMIT 5
    """).fetchall()

    # Memory utilization (how often memories are used)
    utilized_counts = db.execute("""
        SELECT utilized FROM task WHERE utilized != '[]'
    """).fetchall()

    memory_usage = {}
    for row in utilized_counts:
        for mem in json.loads(row["utilized"]):
            memory_usage[mem] = memory_usage.get(mem, 0) + 1

    top_memories = sorted(memory_usage.items(), key=lambda x: -x[1])[:10]

    return {
        "total_snapshots": total_snapshots,
        "total_tasks": total_tasks,
        "status_distribution": {r["status"]: r["count"] for r in status_dist},
        "block_rate": blocked / total_tasks if total_tasks > 0 else 0,
        "avg_tasks_per_plan": round(avg_tasks, 1),
        "frameworks": {r["framework"]: r["count"] for r in frameworks},
        "top_utilized_memories": dict(top_memories),
    }


# =============================================================================
# CLI
# =============================================================================

def _format_task_summary(task: Task) -> str:
    """Format a task for display."""
    status_icon = {
        "pending": " ",
        "in_progress": "~",
        "completed": "+" if not task.delivered.startswith("BLOCKED:") else "X"
    }.get(task.status, "?")

    return f"[{status_icon}] {task.subject}: {task.description[:50]}..."


def _cli():
    import argparse

    parser = argparse.ArgumentParser(
        description="Task snapshot and persistence utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # snapshot
    p = subparsers.add_parser("snapshot", help="Capture current tasks to database")
    p.add_argument("--task-list-id", help="Claude Code task list ID")
    p.add_argument("--notes", default="", help="Notes for this snapshot")
    p.add_argument("--tasks-json", help="JSON string of tasks (for piping)")

    # current
    p = subparsers.add_parser("current", help="Show current tasks (no persistence)")
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # list
    p = subparsers.add_parser("list", help="List all snapshots")
    p.add_argument("--limit", type=int, default=20, help="Max snapshots to show")

    # show
    p = subparsers.add_parser("show", help="Show tasks from a snapshot")
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--json", action="store_true", help="Output as JSON")

    # export
    p = subparsers.add_parser("export", help="Export snapshot to JSON")
    p.add_argument("--snapshot-id", type=int, required=True)
    p.add_argument("--output", "-o", help="Output file (default: stdout)")

    # analyze
    subparsers.add_parser("analyze", help="Analyze patterns across snapshots")

    # schema
    subparsers.add_parser("schema", help="Show database schema")

    args = parser.parse_args()

    if args.command == "snapshot":
        # Parse tasks from JSON input
        if args.tasks_json:
            tasks_data = json.loads(args.tasks_json)
            tasks = [parse_claude_task(t) for t in tasks_data]
        else:
            print("Note: Reading tasks from stdin (paste JSON and press Ctrl+D)")
            import sys
            tasks_data = json.load(sys.stdin)
            if isinstance(tasks_data, list):
                tasks = [parse_claude_task(t) for t in tasks_data]
            else:
                tasks = [parse_claude_task(tasks_data)]

        task_list_id = args.task_list_id or read_task_list_from_env()
        snapshot = capture_snapshot(tasks, task_list_id, args.notes)
        result = save_snapshot(snapshot)
        print(json.dumps(result, indent=2))

    elif args.command == "current":
        print("Note: Provide tasks JSON via stdin")
        import sys
        tasks_data = json.load(sys.stdin)
        tasks = [parse_claude_task(t) for t in tasks_data] if isinstance(tasks_data, list) else [parse_claude_task(tasks_data)]

        if args.json:
            print(json.dumps([asdict(t) for t in tasks], indent=2))
        else:
            plan = reconstruct_plan_from_tasks(tasks)
            print(f"\nPlan Status: {plan.status}")
            print(f"Tasks: {plan.task_count} total, {plan.completed_count} completed, {plan.pending_count} pending")
            print(f"Blocked: {plan.blocked_count}")
            print("\nTasks:")
            for task in tasks:
                print(f"  {_format_task_summary(task)}")

    elif args.command == "list":
        snapshots = list_snapshots(args.limit)
        if not snapshots:
            print("No snapshots found")
            return

        print(f"\n{'ID':<5} {'Captured':<20} {'Status':<10} {'Tasks':<8} {'Objective'}")
        print("-" * 80)
        for s in snapshots:
            print(f"{s['id']:<5} {s['captured_at'][:19]:<20} {s['status']:<10} {s['completed']}/{s['task_count']:<5} {s['objective']}")

    elif args.command == "show":
        snapshot = load_snapshot(args.snapshot_id)
        if not snapshot:
            print(f"Snapshot {args.snapshot_id} not found")
            return

        if args.json:
            output = {
                "snapshot_id": snapshot.id,
                "captured_at": snapshot.captured_at,
                "plan": {
                    "objective": snapshot.plan.objective,
                    "status": snapshot.plan.status,
                    "framework": snapshot.plan.framework,
                    "task_count": snapshot.plan.task_count,
                },
                "tasks": [asdict(t) for t in snapshot.plan.tasks]
            }
            print(json.dumps(output, indent=2))
        else:
            plan = snapshot.plan
            print(f"\nSnapshot #{snapshot.id} captured at {snapshot.captured_at}")
            print(f"Hash: {snapshot.content_hash}")
            if snapshot.notes:
                print(f"Notes: {snapshot.notes}")
            print(f"\nObjective: {plan.objective}")
            print(f"Status: {plan.status}")
            print(f"Framework: {plan.framework or 'none'}")
            print(f"\nTasks ({plan.task_count}):")
            for task in plan.tasks:
                print(f"  {_format_task_summary(task)}")
                if task.delivered:
                    print(f"    -> {task.delivered[:70]}...")

    elif args.command == "export":
        snapshot = load_snapshot(args.snapshot_id)
        if not snapshot:
            print(f"Snapshot {args.snapshot_id} not found")
            return

        output = {
            "snapshot": {
                "id": snapshot.id,
                "captured_at": snapshot.captured_at,
                "content_hash": snapshot.content_hash,
                "source": snapshot.source,
                "notes": snapshot.notes,
            },
            "plan": {
                "objective": snapshot.plan.objective,
                "framework": snapshot.plan.framework,
                "idioms": snapshot.plan.idioms,
                "status": snapshot.plan.status,
                "task_list_id": snapshot.plan.task_list_id,
            },
            "tasks": [asdict(t) for t in snapshot.plan.tasks]
        }

        if args.output:
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
            print(f"Exported to {args.output}")
        else:
            print(json.dumps(output, indent=2))

    elif args.command == "analyze":
        analysis = analyze_snapshots()
        print(json.dumps(analysis, indent=2))

    elif args.command == "schema":
        print("""
Task Snapshot Database Schema
=============================

snapshot
--------
- id: Primary key
- content_hash: SHA256 hash for deduplication
- source: Where snapshot came from (claude_code)
- notes: Optional notes
- captured_at: Timestamp

plan
----
- id: Primary key
- snapshot_id: Foreign key to snapshot
- objective: What the plan accomplishes
- framework: Detected framework
- idioms: JSON {required: [], forbidden: []}
- task_list_id: CLAUDE_CODE_TASK_LIST_ID
- session_id: Session identifier
- status: active/complete/stuck
- created_at, completed_at: Timestamps

task
----
- id: Primary key
- plan_id: Foreign key to plan
- task_id: Claude Code's native ID
- subject: "001: slug" format
- description: Task objective
- status: pending/in_progress/completed
- seq, slug: Parsed from subject
- blocked_by, blocks: JSON arrays of task IDs
- owner: Agent that claimed task
- delta: JSON array of files
- verify: Verification command
- budget: Tool call budget
- framework, idioms: Task-specific overrides
- delivered: Result summary
- utilized: JSON array of memory names
- created_at, completed_at: Timestamps
        """)


if __name__ == "__main__":
    _cli()
