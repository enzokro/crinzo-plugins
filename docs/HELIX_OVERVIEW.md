# Helix - Technical Reference

A Claude Code orchestrator with integrated memory that learns from every session.

## Architecture

Helix is prose-driven: SKILL.md contains orchestration logic; Python utilities provide the muscle.

```
┌─────────────────────────────────────────────────────────────┐
│                    SKILL.md (Orchestrator)                  │
│  State: implicit in conversation flow                       │
│  Source of truth: TaskList metadata (helix_outcome)         │
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│  Explorer     │    │   Planner     │    │   Builder     │
│  (haiku)      │    │   (opus)      │    │   (opus)      │
│  agents/      │    │   agents/     │    │   agents/     │
│  explorer.md  │    │   planner.md  │    │   builder.md  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Utilities                          │
│  lib/memory/core.py  - 9 core + 2 code-assisted primitives  │
│  lib/context.py      - Dual-query context building          │
│  lib/tasks.py        - Output parsing, task state derivation│
│  lib/dag_utils.py    - Cycle detection, stall detection     │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    .helix/helix.db (SQLite)                 │
│  memory, memory_edge, memory_file_pattern                   │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Learning extraction is orchestrator judgment, not a separate agent. The orchestrator decides:
- What delta to pass to `feedback()`
- When to create edges and what type
- When to store systemic patterns (3+ occurrences)
- What to learn vs. skip

## Agents

Three agents with distinct roles:

| Agent | Model | Purpose | Tools |
|-------|-------|---------|-------|
| **Explorer** | Haiku | Parallel reconnaissance | Read, Grep, Glob, Bash |
| **Planner** | Opus | Task decomposition | Read, Grep, Glob, Bash, TaskCreate, TaskUpdate |
| **Builder** | Opus | Task execution | Read, Write, Edit, Grep, Glob, Bash, TaskUpdate |

### Explorer (`agents/explorer.md`)

Explores ONE scope as part of a parallel swarm. Returns JSON findings.

Input:
- `scope`: Directory path or "memory"
- `focus`: What to find within scope
- `objective`: User goal for context

Output (JSON):
```json
{
  "scope": "src/api/",
  "focus": "route handlers",
  "status": "success",
  "findings": [{"file": "...", "what": "...", "relevance": "..."}],
  "framework": {"detected": "...", "confidence": "HIGH|MEDIUM|LOW"},
  "memories": [{"name": "...", "trigger": "...", "why": "..."}]
}
```

### Planner (`agents/planner.md`)

Decomposes objective into task DAG using Claude Code's native Task system.

Input:
- `objective`: What to build
- `exploration`: Merged explorer findings

Output:
```
TASK_MAPPING:
001 -> task-abc123
002 -> task-def456

PLAN_COMPLETE: 2 tasks
```

Or clarification request:
```json
{"decision": "CLARIFY", "questions": ["..."]}
```

### Builder (`agents/builder.md`)

Executes a single task. Reports DELIVERED or BLOCKED.

Input:
- `task_id`: Unique task identifier
- `objective`: What to build
- `verify`: Command to prove success
- `relevant_files`: Files to read first
- `failures_to_avoid`: Memory hints (with confidence: `[75%]` or `[unproven]`)
- `patterns_to_apply`: Memory hints
- `parent_deliveries`: Context from completed blockers
- `warning`: Systemic issue to address first

Output:
```
DELIVERED: <one-line summary>
```
Or:
```
BLOCKED: <reason>
TRIED: <what attempted>
ERROR: <message>
```

Task update before text output:
```
TaskUpdate(taskId="...", status="completed", metadata={"helix_outcome": "delivered"|"blocked", ...})
```

## Memory System

### Types

| Type | Purpose | When stored |
|------|---------|-------------|
| **failure** | Something that went wrong | Builder blocks with generalizable cause |
| **pattern** | Successful approach | Success required non-obvious discovery |
| **systemic** | Recurring issue | Same failure pattern 3+ times |

### 9 Core + 2 Code-Assisted (`lib/memory/core.py`)

```python
# 9 Core Primitives
store(trigger, resolution, type, source)  # → {"status": "added"|"merged", "name": "..."}
recall(query, type, limit, expand)        # → [memories with _score, _relevance, _recency]
get(name)                                  # → single memory dict
edge(from_name, to_name, rel_type, weight) # → create/strengthen relationship
edges(name, rel_type)                      # → query relationships
feedback(names, delta)                     # → update scores
decay(unused_days, min_uses)              # → halve scores on dormant memories
prune(min_effectiveness, min_uses)        # → remove low performers
health()                                   # → system status

# 2 Code-Assisted (surfaces facts, orchestrator decides)
similar_recent(trigger, threshold, days, type)  # → systemic detection candidates
suggest_edges(memory_name, limit)               # → edge creation candidates
```

### Scoring Formula

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)

relevance = cosine_similarity(query_embedding, memory_embedding)
effectiveness = helped / (helped + failed)  # default 0.5 if no feedback
recency = 2^(-days_since_use / 7)           # ACT-R decay, 7-day half-life
```

### Graph System

Edge types:
- **solves**: Pattern's resolution solved a failure
- **co_occurs**: Both memories helped same task
- **causes**: Failure A led to discovering failure B
- **similar**: Conceptual overlap worth preserving

Graph expansion (`--expand` flag) surfaces solutions connected to relevant failures.

### Dual-Query Strategy (`lib/context.py`)

Context builder uses two query paths:
1. **Semantic search** on objective (natural language)
2. **File pattern matching** on relevant files

Results are merged, deduped, and ranked by effectiveness.

Memory hints include confidence indicators:
- `[75%]` = Memory helped 75% of the time
- `[unproven]` = Not enough usage data yet

## Context Flow

### Lineage Protocol

Parent deliveries passed to builders:
```json
[
  {"seq": "001", "slug": "setup-auth", "delivered": "Created AuthService with JWT support"},
  {"seq": "002", "slug": "add-routes", "delivered": "Added /login and /logout endpoints"}
]
```

Builders use this context to understand what blockers produced.

### Warning Injection

Systemic issues placed at prompt start (priority):
```
WARNING: Repeated circular import failures in this codebase. Check imports before adding new dependencies.
```

## Database Schema

SQLite database at `.helix/helix.db` (WAL mode, write lock for safe writes):

```sql
-- Schema versioning
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Memories: learned failures, patterns, and systemic issues
CREATE TABLE memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,                -- failure, pattern, systemic
    trigger TEXT NOT NULL,
    resolution TEXT NOT NULL,
    helped REAL DEFAULT 0,
    failed REAL DEFAULT 0,
    embedding BLOB,
    source TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_used TEXT,
    file_patterns TEXT                 -- JSON array of extracted patterns
);

-- Memory relationships (graph edges)
CREATE TABLE memory_edge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_name TEXT NOT NULL,
    to_name TEXT NOT NULL,
    rel_type TEXT NOT NULL,            -- solves, co_occurs, similar, causes
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    UNIQUE(from_name, to_name, rel_type)
);

-- Normalized file patterns for efficient lookup
CREATE TABLE memory_file_pattern (
    memory_name TEXT NOT NULL,
    pattern TEXT NOT NULL,
    PRIMARY KEY (memory_name, pattern),
    FOREIGN KEY (memory_name) REFERENCES memory(name) ON DELETE CASCADE
);
```

**Note**: Plan, workspace, and exploration tables were removed in schema v2 migration. Task management is handled by Claude Code's native Task system with metadata.

## DAG Utilities (`lib/dag_utils.py`)

```python
detect_cycles(dependencies)     # → List of cycles found
get_completed_task_ids(tasks)   # → IDs with helix_outcome="delivered"
get_blocked_task_ids(tasks)     # → IDs with helix_outcome="blocked"
get_ready_tasks(tasks)          # → IDs ready for execution
check_stalled(tasks)            # → (is_stalled, stall_info)
clear_checkpoints()             # → Clear all checkpoints
```

## Task Utilities (`lib/tasks.py`)

```python
parse_builder_output(output)   # → {"status": "delivered"|"blocked", "summary": "...", ...}
helix_task_state(task)         # → {"executable", "finished", "successful", "outcome", "blocks_dependents"}
```

Derives canonical task state from dual status model (native `status` + `helix_outcome` metadata).

## CLI Reference

### Memory Operations

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."

# Recall (with graph expansion)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Get single memory
python3 "$HELIX/lib/memory/core.py" get "memory-name"

# Create edge
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves --weight 1.0

# Query edges
python3 "$HELIX/lib/memory/core.py" edges --name "memory-name"
python3 "$HELIX/lib/memory/core.py" edges --rel solves

# Feedback
python3 "$HELIX/lib/memory/core.py" feedback --names '["mem1", "mem2"]' --delta 0.5

# Decay
python3 "$HELIX/lib/memory/core.py" decay --days 30 --min-uses 2
python3 "$HELIX/lib/memory/core.py" decay-edges --days 60

# Prune
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Consolidate
python3 "$HELIX/lib/memory/core.py" consolidate

# Health
python3 "$HELIX/lib/memory/core.py" health

# SOAR chunking
python3 "$HELIX/lib/memory/core.py" chunk --task "..." --outcome "success..." --approach "..."

# Code-assisted (surfaces facts, orchestrator decides)
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7 --type failure
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
```

### Task Operations

```bash
# Parse builder output
python3 "$HELIX/lib/tasks.py" parse-output "$output"
```

### Context Operations

```bash
# Build context from task data
python3 "$HELIX/lib/context.py" build-context --task-data '{...}' --lineage '[...]'

# Build lineage from completed tasks
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[...]'
```

### DAG Operations

```bash
# Clear checkpoints
python3 "$HELIX/lib/dag_utils.py" clear

# Detect cycles
python3 "$HELIX/lib/dag_utils.py" detect-cycles --dependencies '{...}'

# Check stalled
python3 "$HELIX/lib/dag_utils.py" check-stalled --tasks '[...]'
```

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: explore → plan → build |
| `/helix-query <text>` | Search memory by meaning (with graph expansion) |
| `/helix-stats` | Memory health metrics |

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `HELIX_DB_PATH` | Custom database location | `.helix/helix.db` |
| `HELIX_PLUGIN_ROOT` | Plugin root path | Read from `.helix/plugin_root` |

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `DECAY_HALF_LIFE_DAYS` | 7 | Recency score half-life |
| `DUPLICATE_THRESHOLD` | 0.85 | Semantic deduplication threshold |
| `SCORE_WEIGHTS` | 0.5/0.3/0.2 | Relevance/effectiveness/recency |
| `VALID_TYPES` | failure, pattern, systemic | Allowed memory types |

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── agents/
│   ├── explorer.md           # Parallel reconnaissance (haiku)
│   ├── planner.md            # Task decomposition (opus)
│   └── builder.md            # Task execution (opus)
├── lib/
│   ├── __init__.py           # Version: 2.0.0
│   ├── memory/
│   │   ├── __init__.py       # Clean exports
│   │   ├── core.py           # 9 core + 2 code-assisted primitives
│   │   └── embeddings.py     # all-MiniLM-L6-v2
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py     # SQLite singleton, WAL, write_lock
│   │   └── schema.py         # Memory, MemoryEdge dataclasses
│   ├── context.py            # Dual-query context building
│   ├── tasks.py              # Output parsing, task state derivation
│   └── dag_utils.py          # Cycle detection, stall detection
├── scripts/
│   ├── setup-env.sh          # SessionStart hook
│   └── init.sh               # Database initialization
├── skills/
│   ├── helix/
│   │   ├── SKILL.md          # Main orchestrator
│   │   └── reference/        # Decision tables (feedback, edges, stall, etc.)
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
└── .helix/                   # Runtime (created on first use)
    ├── helix.db              # SQLite database
    └── plugin_root           # Plugin path for sub-agents
```

## When to Use

**Use helix when:**
- Multi-step work requiring exploration first
- Similar work has been done before (leverage learned context)
- Verification needed at each phase
- Past failures should inform future work

**Skip helix when:**
- Simple single-file changes
- Exploratory prototyping
- Quick one-offs with no future value
- Work that doesn't benefit from learned context

## What Helix Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user collaboration tool (single-user, local SQLite)
- A model-agnostic framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
