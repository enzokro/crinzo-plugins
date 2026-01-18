# FTL Complete Database Refactoring Plan

## Goal

Eliminate ALL file-based state. Everything flows through `.ftl/ftl.db`. Clean break, no legacy support.

---

## Current File Operations to Eliminate

| Location | File Pattern | Action |
|----------|--------------|--------|
| `orchestration.py` | `.ftl/cache/explorer_*.json` | **DELETE** - Use `explorer_result` table |
| `exploration.py` | `.ftl/cache/explorer_*.json` | **DELETE** - Use `explorer_result` table |
| `exploration.py` | `EXPLORATION_FILE` constant | **DELETE** |
| `memory.py` | `MEMORY_FILE` constant | **DELETE** |
| `phase.py` | `PHASE_STATE_FILE` constant | **DELETE** |
| `workspace.py` | `plan.json` file input | **DELETE** - Use `plan` table |
| `benchmark.py` | `.ftl/benchmark/` directory | **DELETE** - Use `benchmark` table |
| `agents/explorer.md` | Write to cache files | **REPLACE** - Write to database |

**Keep**: `.ftl/ftl.log` (logs are fine as files)

---

## New Database Schema

Add to `lib/db/schema.py`:

```python
@dataclass
class ExplorerResult:
    """Individual explorer mode output (staging before aggregation)."""
    id: int = field(default=None)
    session_id: str = ""           # UUID linking parallel explorers
    mode: str = ""                 # structure|pattern|memory|delta
    status: str = "pending"        # pending|ok|partial|error
    result: str = "{}"             # JSON: mode-specific output
    created_at: str = ""


@dataclass
class Plan:
    """Task plan from planner agent."""
    id: int = field(default=None)
    campaign_id: Optional[int] = None
    objective: str = ""
    framework: Optional[str] = None
    idioms: str = "{}"             # JSON: {required, forbidden}
    tasks: str = "[]"              # JSON: task array
    created_at: str = ""
    status: str = "active"         # active|executed|superseded


@dataclass
class Benchmark:
    """Performance benchmark results."""
    id: int = field(default=None)
    run_id: str = ""               # UUID for benchmark run
    metric: str = ""               # memory_size|query_time|etc
    value: float = 0.0
    metadata: str = "{}"           # JSON
    created_at: str = ""
```

---

## Phase 1: Schema & Infrastructure

### 1.1 Update `lib/db/schema.py`

Add three new dataclasses: `ExplorerResult`, `Plan`, `Benchmark`

### 1.2 Update `lib/db/connection.py`

Register new tables in `init_db()`:
```python
db.t.explorer_result
db.t.plan
db.t.benchmark
```

### 1.3 Create `lib/plan.py`

New module for plan operations:

```python
"""Plan storage and retrieval."""

def write(plan_dict: dict) -> int:
    """Store plan in database, return ID."""
    db = get_db()
    plan = Plan(
        campaign_id=plan_dict.get("campaign_id"),
        objective=plan_dict["objective"],
        framework=plan_dict.get("framework"),
        idioms=json.dumps(plan_dict.get("idioms", {})),
        tasks=json.dumps(plan_dict["tasks"]),
        created_at=datetime.now().isoformat(),
        status="active"
    )
    result = db.t.plan.insert(plan)
    return result.id


def read(plan_id: int) -> dict:
    """Get plan by ID."""
    db = get_db()
    row = db.t.plan[plan_id]
    return {
        "id": row.id,
        "objective": row.objective,
        "framework": row.framework,
        "idioms": json.loads(row.idioms),
        "tasks": json.loads(row.tasks),
        "status": row.status
    }


def get_active() -> dict | None:
    """Get most recent active plan."""
    db = get_db()
    rows = list(db.t.plan.rows_where("status = ?", ["active"]))
    if not rows:
        return None
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    return read(rows[0]["id"])


def mark_executed(plan_id: int):
    """Mark plan as executed."""
    db = get_db()
    db.t.plan.update({"status": "executed"}, plan_id)


# CLI: write, read, get-active, mark-executed
```

---

## Phase 2: Explorer Flow Refactoring

### 2.1 Update `lib/exploration.py`

**Remove:**
- `EXPLORATION_FILE` constant
- `aggregate_files()` function

**Add:**
```python
def write_result(session_id: str, mode: str, result: dict) -> dict:
    """Write individual explorer result to database."""
    db = get_db()
    er = ExplorerResult(
        session_id=session_id,
        mode=mode,
        status=result.get("status", "ok"),
        result=json.dumps(result),
        created_at=datetime.now().isoformat()
    )
    db.t.explorer_result.insert(er)
    return {"session_id": session_id, "mode": mode, "status": "written"}


def get_session_status(session_id: str) -> dict:
    """Get completion status for exploration session."""
    db = get_db()
    rows = list(db.t.explorer_result.rows_where(
        "session_id = ?", [session_id]
    ))
    completed = [r["mode"] for r in rows if r["status"] in ["ok", "partial", "error"]]
    missing = [m for m in ["structure", "pattern", "memory", "delta"] if m not in completed]
    return {
        "completed": completed,
        "missing": missing,
        "total": len(completed),
        "quorum_met": len(completed) >= 3
    }


def aggregate_session(session_id: str, objective: str = None) -> dict:
    """Aggregate explorer results from database session."""
    db = get_db()
    rows = list(db.t.explorer_result.rows_where(
        "session_id = ?", [session_id]
    ))
    results = [json.loads(r["result"]) for r in rows]
    return aggregate(results, objective)


def clear_session(session_id: str) -> int:
    """Delete explorer results for a session."""
    db = get_db()
    rows = list(db.t.explorer_result.rows_where("session_id = ?", [session_id]))
    for row in rows:
        db.t.explorer_result.delete(row["id"])
    return len(rows)
```

**Update CLI:**
```
write-result --session ID --mode MODE < result.json
session-status --session ID
aggregate-session --session ID --objective "text"
clear-session --session ID
```

### 2.2 Update `lib/orchestration.py`

**Remove:**
- `CACHE_DIR` constant
- All file-based polling logic

**Replace `wait_explorers()`:**
```python
def wait_explorers(
    session_id: str,
    required: int = 3,
    timeout: int = 300,
    poll_interval: float = 2.0
) -> dict:
    """Wait for explorer agents using database queries."""
    from lib.exploration import get_session_status

    start = time.time()

    while True:
        elapsed = time.time() - start
        status = get_session_status(session_id)

        if len(status["completed"]) >= 4:
            return {
                "status": "all_complete",
                "completed": status["completed"],
                "missing": [],
                "elapsed": round(elapsed, 2)
            }

        if len(status["completed"]) >= required:
            return {
                "status": "quorum_met",
                "completed": status["completed"],
                "missing": status["missing"],
                "elapsed": round(elapsed, 2)
            }

        if elapsed >= timeout:
            return {
                "status": "timeout",
                "completed": status["completed"],
                "missing": status["missing"],
                "elapsed": round(elapsed, 2)
            }

        time.sleep(poll_interval)


def check_explorers(session_id: str) -> dict:
    """Non-blocking check of explorer status."""
    from lib.exploration import get_session_status
    return get_session_status(session_id)


def create_session() -> str:
    """Generate new exploration session ID."""
    import uuid
    return str(uuid.uuid4())[:8]
```

**Update CLI:**
```
wait-explorers --session ID [--required N] [--timeout S]
check-explorers --session ID
create-session
```

---

## Phase 3: Workspace Flow Refactoring

### 3.1 Update `lib/workspace.py`

**Remove:**
- `--plan PATH` argument (file-based)

**Replace with:**
```python
def create(plan_id: int = None, task_seq: str = None) -> list:
    """Create workspace(s) from stored plan.

    Args:
        plan_id: ID of plan in database (required)
        task_seq: Specific task sequence (optional, creates all if omitted)

    Returns:
        List of created workspace IDs
    """
    from lib.plan import read as read_plan

    plan = read_plan(plan_id)
    # ... rest of creation logic using plan dict
```

**Update CLI:**
```
create --plan-id ID [--task SEQ]
```

### 3.2 Update Plan → Workspace Flow

**Old:**
```
Planner → plan.json file → workspace.py create --plan plan.json
```

**New:**
```
Planner → stdout JSON → plan.py write (returns ID) → workspace.py create --plan-id ID
```

In SKILL.md state machine:
```
STATE: REGISTER
  DO: plan_id = python3 lib/plan.py write < plan_output.json
  DO: python3 lib/workspace.py create --plan-id $plan_id
```

---

## Phase 4: Benchmark Refactoring

### 4.1 Update `lib/benchmark.py`

**Remove:**
- `BENCHMARK_DIR` constant
- All file I/O operations

**Replace with:**
```python
def record_metric(run_id: str, metric: str, value: float, metadata: dict = None):
    """Record benchmark metric to database."""
    db = get_db()
    db.t.benchmark.insert(Benchmark(
        run_id=run_id,
        metric=metric,
        value=value,
        metadata=json.dumps(metadata or {}),
        created_at=datetime.now().isoformat()
    ))


def get_run(run_id: str) -> list:
    """Get all metrics for a benchmark run."""
    db = get_db()
    return list(db.t.benchmark.rows_where("run_id = ?", [run_id]))


def compare_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two benchmark runs."""
    a = {r["metric"]: r["value"] for r in get_run(run_id_a)}
    b = {r["metric"]: r["value"] for r in get_run(run_id_b)}
    return {
        metric: {"a": a.get(metric), "b": b.get(metric)}
        for metric in set(a.keys()) | set(b.keys())
    }
```

---

## Phase 5: Legacy Cleanup

### 5.1 Remove Dead Constants

| File | Remove |
|------|--------|
| `exploration.py` | `EXPLORATION_FILE = Path(".ftl/exploration.json")` |
| `memory.py` | `MEMORY_FILE = Path(".ftl/memory.json")` |
| `phase.py` | `PHASE_STATE_FILE = Path(".ftl/phase_state.json")` |

### 5.2 Remove Cache Directory Handling

Delete from codebase:
- Any reference to `.ftl/cache/`
- Any `mkdir -p .ftl/cache` commands
- `scripts/cleanup-env.sh` cache cleanup lines

### 5.3 Clean .ftl Directory Structure

**Before:**
```
.ftl/
├── ftl.db
├── ftl.log
├── cache/
│   └── explorer_*.json
├── workspace/          # virtual, doesn't exist
├── plan.json          # transient
└── plugin_root
```

**After:**
```
.ftl/
├── ftl.db             # ALL state
├── ftl.log            # logs only
└── plugin_root        # marker file
```

---

## Phase 6: Agent Protocol Updates

### 6.1 Update `agents/explorer.md`

**Remove:**
```
Write to `.ftl/cache/explorer_{mode}.json`
```

**Replace with:**
```
## Output Protocol

Write result directly to database:

```bash
python3 "$(cat .ftl/plugin_root)/lib/exploration.py" write-result \
    --session "$SESSION_ID" \
    --mode "{mode}" <<< '{...json result...}'
```

The SESSION_ID is provided by the orchestrator at exploration start.
```

### 6.2 Update `skills/ftl/SKILL.md`

**Update INIT_PATTERN:**
```
EMIT: STATE_ENTRY state=INIT [mode={mode}]
DO: mkdir -p .ftl && echo "${CLAUDE_PLUGIN_ROOT}" > .ftl/plugin_root
DO: session_id = python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py create-session
EMIT: PHASE_TRANSITION from=init to=explore
GOTO: EXPLORE with session_id
```

**Update EXPLORE_PATTERN:**
```
EMIT: STATE_ENTRY state=EXPLORE session_id={session_id}
DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
    - Task(ftl:ftl-explorer) "mode=structure, session_id={session_id}"
    - Task(ftl:ftl-explorer) "mode=pattern, session_id={session_id}, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=memory, session_id={session_id}, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=delta, session_id={session_id}, objective={objective}"
WAIT: Quorum via database
  CHECK: python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py wait-explorers --session {session_id} --required=3 --timeout=300
  IF: wait_result=="quorum_met" OR wait_result=="all_complete" → PROCEED
  IF: wait_result=="timeout" → EMIT: PARTIAL_FAILURE, PROCEED
  IF: wait_result=="quorum_failure" → GOTO ERROR
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-session --session {session_id} --objective "{objective}"
DO: | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
EMIT: PHASE_TRANSITION from=explore to=plan
GOTO: PLAN
```

**Update BUILD flow:**
```
STATE: REGISTER
  EMIT: STATE_ENTRY state=REGISTER
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "{objective}"
  DO: plan_id = python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py write < plan.json
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id $plan_id
  EMIT: PHASE_TRANSITION from=register to=execute
  GOTO: EXECUTE
```

---

## Phase 7: Documentation Updates

### Files to Update

| File | Changes |
|------|---------|
| `agents/explorer.md` | New output protocol |
| `agents/shared/EXPLORER_SCHEMAS.md` | Remove cache file references |
| `agents/shared/OUTPUT_TEMPLATES.md` | Remove cache file references |
| `skills/ftl/SKILL.md` | Session-based flow |
| `skills/ftl/references/CLI_REFERENCE.md` | New commands, remove file refs |
| `skills/ftl/references/DATABASE_SCHEMA.md` | Add new tables |
| `skills/ftl/references/WORKSPACE_SPEC.md` | Remove cache directory |
| `README.md` | Update architecture section |

---

## Implementation Checklist

### Batch 1: Database Schema
- [ ] Add `ExplorerResult` to `lib/db/schema.py`
- [ ] Add `Plan` to `lib/db/schema.py`
- [ ] Add `Benchmark` to `lib/db/schema.py`
- [ ] Update `lib/db/connection.py` to register tables
- [ ] Create `lib/plan.py` module

### Batch 2: Explorer Refactoring
- [ ] Add `write_result()` to `lib/exploration.py`
- [ ] Add `get_session_status()` to `lib/exploration.py`
- [ ] Add `aggregate_session()` to `lib/exploration.py`
- [ ] Remove `aggregate_files()` from `lib/exploration.py`
- [ ] Remove `EXPLORATION_FILE` constant
- [ ] Update exploration CLI commands

### Batch 3: Orchestration Refactoring
- [ ] Add `create_session()` to `lib/orchestration.py`
- [ ] Rewrite `wait_explorers()` for database
- [ ] Rewrite `check_explorers()` for database
- [ ] Remove `CACHE_DIR` constant
- [ ] Update orchestration CLI commands

### Batch 4: Workspace Refactoring
- [ ] Update `workspace.py` to use `--plan-id`
- [ ] Remove `--plan` file argument
- [ ] Update workspace creation to read from plan table

### Batch 5: Benchmark Refactoring
- [ ] Rewrite `lib/benchmark.py` for database
- [ ] Remove `BENCHMARK_DIR` constant
- [ ] Update benchmark CLI commands

### Batch 6: Legacy Cleanup
- [ ] Remove `MEMORY_FILE` from `lib/memory.py`
- [ ] Remove `PHASE_STATE_FILE` from `lib/phase.py`
- [ ] Remove cache directory references from scripts
- [ ] Delete any `.ftl/cache/` mkdir commands

### Batch 7: Agent Updates
- [ ] Update `agents/explorer.md` output protocol
- [ ] Update `agents/shared/EXPLORER_SCHEMAS.md`
- [ ] Update `agents/shared/OUTPUT_TEMPLATES.md`

### Batch 8: SKILL.md Updates
- [ ] Add session_id to INIT_PATTERN
- [ ] Update EXPLORE_PATTERN for database
- [ ] Update REGISTER state for plan-id
- [ ] Update all file references

### Batch 9: Reference Docs
- [ ] Update `CLI_REFERENCE.md`
- [ ] Update `DATABASE_SCHEMA.md`
- [ ] Update `WORKSPACE_SPEC.md`
- [ ] Update `README.md`

### Batch 10: Testing
- [ ] Update `tests/conftest.py` fixtures
- [ ] Update `tests/test_exploration.py`
- [ ] Update `tests/test_workspace.py`
- [ ] Run full test suite
- [ ] Manual end-to-end test

---

## Final State

```
.ftl/
├── ftl.db      # Everything
└── ftl.log     # Logs

Database tables:
├── memory          # Failures + patterns
├── memory_edge     # Graph relationships
├── campaign        # Campaign state + tasks
├── workspace       # Workspace records
├── archive         # Completed campaigns
├── exploration     # Aggregated explorer data
├── explorer_result # Individual explorer outputs (NEW)
├── plan            # Plans from planner (NEW)
├── benchmark       # Performance metrics (NEW)
├── phase_state     # Workflow phase
└── event           # Audit log
```

No JSON files. No XML files. No cache directories. Just the database.
