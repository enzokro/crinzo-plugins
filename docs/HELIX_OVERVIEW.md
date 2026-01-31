# Helix - Technical Reference

A Claude Code orchestrator with integrated memory that learns from every session.

## Architecture

Helix is prose-driven: SKILL.md contains orchestration logic; Python utilities provide the muscle.

```
┌─────────────────────────────────────────────────────────────┐
│                    SKILL.md (Orchestrator)                  │
│  Judgment: what to explore, what to store, when to override │
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hook Layer (Invisible)                    │
│  PreToolUse: inject memory    SubagentStop: extract learning │
│  PostToolUse: auto-feedback                                  │
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
│  lib/memory/core.py  - 9 core + 4 maintenance primitives    │
│  lib/hooks/          - Memory injection & learning extraction│
│  lib/context.py      - Agent-specific context building      │
│  lib/prompt_parser.py - Structured field extraction         │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    .helix/helix.db (SQLite)                 │
│  memory, memory_edge, memory_file_pattern                   │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Hooks separate judgment from mechanics. Memory injection, learning extraction, and feedback attribution happen automatically. The orchestrator retains judgment: what to store, when to override feedback, what candidates to keep

## Agents

Three agents with distinct roles:

| Agent | Model | Purpose | Tools | Context Injection |
|-------|-------|---------|-------|-------------------|
| **Explorer** | Haiku | Parallel reconnaissance | Read, Grep, Glob, Bash | Auto: facts, failures |
| **Planner** | Opus | Task decomposition | Read, Grep, Glob, Bash | Auto: decisions, conventions, evolution |
| **Builder** | Opus | Task execution | Read, Write, Edit, Grep, Glob, Bash, TaskUpdate | Auto: all types + lineage |

### Explorer (`agents/explorer.md`)

Explores ONE scope as part of a parallel swarm. Returns JSON findings.

Input:
- `scope`: Directory path or "memory"
- `focus`: What to find within scope
- `objective`: User goal for context
- `known_facts`: Facts already known (skip re-discovery)
- `relevant_failures`: Failures to watch for

Output (JSON):
```json
{
  "scope": "src/api/",
  "focus": "route handlers",
  "status": "success",
  "findings": [
    {
      "file": "src/api/routes.py",
      "what": "REST endpoint definitions",
      "action": "modify|create|reference|test",
      "task_hint": "api-routes"
    }
  ],
  "framework": {"detected": "FastAPI", "confidence": "HIGH", "evidence": "..."},
  "patterns_observed": ["dependency injection", "..."],
  "memories": [{"name": "...", "trigger": "...", "why": "..."}]
}
```

### Planner (`agents/planner.md`)

Decomposes objective into task DAG using Claude Code's native Task system.

Input:
- `objective`: What to build
- `exploration`: Merged explorer findings
- `project_context`: {decisions, conventions, recent_evolution}

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

Task metadata structure:
```json
{
  "seq": "001",
  "relevant_files": ["src/api/routes.py", "src/models/user.py"]
}
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
- `conventions_to_follow`: Project-specific conventions
- `related_facts`: Facts about relevant files
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
TaskUpdate(taskId="...", status="completed", metadata={"helix_outcome": "delivered"|"blocked", "summary": "..."})
```

## Hook System

Helix uses Claude Code hooks for invisible memory operations.

### PreToolUse(Task) Hook

**Files:** `scripts/hooks/pretool-task.sh` → `lib/hooks/inject_memory.py`

Intercepts Task tool calls for helix agents. Parses prompt fields, queries memory graph, enriches prompt with relevant context.

| Agent | Context Block | Memory Types |
|-------|---------------|--------------|
| Explorer | `# MEMORY CONTEXT` | facts, failures |
| Planner | `# PROJECT CONTEXT` | decisions, conventions, evolution |
| Builder | Structured fields | all types via semantic + file search |

**Control:** Add `NO_INJECT: true` to prompt to skip injection.

### SubagentStop Hook

**Files:** `scripts/hooks/subagent-stop.sh` → `lib/hooks/extract_learning.py`

Parses agent transcripts for learning markers. Writes candidates to `.helix/learning-queue/`.

| Agent | Marker | Memory Types |
|-------|--------|--------------|
| Builder | `learned` metadata field | pattern, failure, convention |
| Explorer | FINDINGS section | fact |
| Planner | LEARNED block | decision |

### PostToolUse(TaskUpdate) Hook

**File:** `scripts/hooks/posttool-taskupdate.sh`

Detects `helix_outcome` in TaskUpdate metadata. Auto-credits/debits injected memories:
- **delivered**: +0.5 to `helped`
- **blocked**: -0.3 to `failed`

Correlates with injection state via task_id, then cleans up state file.

### State Files

| Directory | Purpose | Lifecycle |
|-----------|---------|-----------|
| `.helix/injection-state/` | Tracks injected memories | Created on inject, deleted after feedback |
| `.helix/learning-queue/` | Learning candidates | Created on agent stop, deleted after review |

## Prompt Parser (`lib/prompt_parser.py`)

Parses structured fields from Task prompts for hook injection.

**Recognized Fields:**
- Explorer: `SCOPE`, `FOCUS`, `OBJECTIVE`
- Planner: `OBJECTIVE`, `EXPLORATION`
- Builder: `TASK_ID`, `TASK`, `OBJECTIVE`, `VERIFY`, `RELEVANT_FILES`, `LINEAGE`, `WARNING`, `MEMORY_LIMIT`
- Control: `NO_INJECT` (skip injection if "true")

**Functions:**
```python
parse_prompt(prompt)           # → dict with parsed fields
detect_agent_type(prompt)      # → "explorer" | "planner" | "builder"
should_inject(prompt)          # → False if NO_INJECT: true
extract_*_params(prompt)       # → agent-specific parameters
```

## Memory System

### Types

Seven memory types serve different purposes:

| Type | Purpose | When Stored | Decay Half-Life |
|------|---------|-------------|-----------------|
| **failure** | What went wrong and how to fix it | Builder blocks with generalizable cause | 7 days |
| **pattern** | Successful approach to apply | Success required non-obvious discovery | 7 days |
| **systemic** | Recurring issue (3+ occurrences) | Same failure pattern detected 3+ times | 14 days |
| **fact** | Codebase structure and relationships | Explorer finds high-confidence structure | 30 days |
| **convention** | Validated patterns for this project | Builder applies pattern successfully | 14 days |
| **decision** | Architectural choices already made | Planner makes explicit design choice | 30 days |
| **evolution** | What changed recently | Task completes with file changes | 7 days |

### Type-Specific Scoring

Different memory types use different weight profiles:

| Type | Relevance | Effectiveness | Recency |
|------|-----------|---------------|---------|
| failure | 0.5 | 0.3 | 0.2 |
| pattern | 0.5 | 0.3 | 0.2 |
| systemic | 0.6 | 0.3 | 0.1 |
| fact | 0.7 | 0.1 | 0.2 |
| convention | 0.4 | 0.4 | 0.2 |
| decision | 0.6 | 0.2 | 0.2 |
| evolution | 0.4 | 0.1 | 0.5 |

### Primitives (`lib/memory/core.py`)

**9 Core Primitives:**
```python
store(trigger, resolution, type, source)  # → {"status": "added"|"merged", "name": "..."}
recall(query, type, limit, expand)        # → [memories with _score, _relevance, _recency]
recall_by_type(query, types, limit)       # → {type: [memories]} grouped by type
get(name)                                  # → single memory dict
edge(from_name, to_name, rel_type, weight) # → create/strengthen relationship
edges(name, rel_type)                      # → query relationships
feedback(names, delta)                     # → update scores
decay(unused_days, min_uses)              # → halve scores on dormant memories
prune(min_effectiveness, min_uses)        # → remove low performers
health()                                   # → system status
```

**2 Code-Assisted (surfaces facts, orchestrator decides):**
```python
similar_recent(trigger, threshold, days, type)  # → systemic detection candidates
suggest_edges(memory_name, limit)               # → edge creation candidates
```

**3 Maintenance Functions:**
```python
decay_edges(unused_days)        # → decay unused edge weights
consolidate(similarity_threshold)  # → merge highly similar memories
chunk(task, outcome, approach)  # → SOAR-pattern extraction
```

### Scoring Formula

```
score = (relevance_weight × relevance) + (effectiveness_weight × effectiveness) + (recency_weight × recency)

relevance = cosine_similarity(query_embedding, memory_embedding)
effectiveness = helped / (helped + failed)  # default 0.5 if no feedback
recency = 2^(-days_since_use / half_life)   # type-specific half-life
```

### Intent-Aware Query Routing

The `recall` command supports `--intent` for type boosting:

| Intent | Priority Types | Use Case |
|--------|---------------|----------|
| `why` | failure, systemic | Debugging, root cause |
| `how` | pattern, convention | Implementation guidance |
| `what` | fact, decision | Understanding structure |
| `debug` | failure, pattern | Error resolution |

Builder context uses `intent="how"` to boost patterns and conventions.

### Graph System

Edge types:
- **solves**: Pattern's resolution solved a failure
- **co_occurs**: Both memories helped same task
- **causes**: Failure A led to discovering failure B
- **similar**: Conceptual overlap worth preserving

Graph expansion (`--expand` flag) surfaces solutions connected to relevant failures. Edge weights boost scores of graph-discovered memories.

## Observer System (`lib/observer.py`)

Extracts learnings from agent outputs. Orchestrator reviews candidates and decides storage.

### Observer Functions

```python
observe_explorer(output)                    # → candidates (type=fact, convention)
observe_planner(tasks, exploration)         # → candidates (type=decision)
observe_builder(task, result, files_changed) # → candidates (type=evolution, convention, failure)
observe_session(objective, tasks, outcomes)  # → session summary (type=evolution)

should_store(candidate, min_confidence)     # → bool
store_candidates(candidates, min_confidence) # → {stored: [...], skipped: [...]}
```

### Confidence Levels

Candidates include `_confidence` field: high, medium, low

- **high**: We know this happened (task delivered, explicit error)
- **medium**: Strong evidence (pattern detected, decision made)
- **low**: Needs validation through use (observed pattern)

## Context Building (`lib/context.py`)

Context is automatically injected via PreToolUse hook. The orchestrator does not call context.py directly.

### Explorer Context
```python
build_explorer_context(objective, scope, limit=5)
# Returns: {"known_facts": [...], "relevant_failures": [...], "injected": [...]}
```

### Planner Context
```python
build_planner_context(objective, limit=5)
# Returns: {"decisions": [...], "conventions": [...], "recent_evolution": [...], "injected": [...]}
```

### Builder Context
```python
build_context(task_data, lineage=None, memory_limit=5, warning=None)
# Returns: {"prompt": "...", "injected": ["memory-name-1", ...]}
```

Builder context includes:
- `FAILURES_TO_AVOID`: Error patterns with `[effectiveness%]` scores
- `PATTERNS_TO_APPLY`: Proven techniques
- `CONVENTIONS_TO_FOLLOW`: Project standards
- `RELATED_FACTS`: Context about relevant files
- `INJECTED_MEMORIES`: List of memory names for feedback tracking

### Manual Override

Add `NO_INJECT: true` to prompt to skip automatic injection and call context.py directly:
```bash
python3 "$HELIX/lib/context.py" build-context --task-data '...' --lineage '...'
```

### Lineage Protocol

Parent deliveries passed to builders:
```json
[
  {"seq": "001", "slug": "setup-auth", "delivered": "Created AuthService with JWT support"},
  {"seq": "002", "slug": "add-routes", "delivered": "Added /login and /logout endpoints"}
]
```

### Warning Injection

Systemic issues placed at prompt start (priority):
```
WARNING: Repeated circular import failures in this codebase. Check imports before adding new dependencies.
```

## Task System

### Dual Status Model

**Native `status`** controls DAG execution: pending → in_progress → completed
**Helix `helix_outcome`** captures semantic result: delivered | blocked | skipped

| status | helix_outcome | Meaning |
|--------|---------------|---------|
| completed | delivered | Success, memory credit |
| completed | blocked | Finished but didn't achieve goal |
| completed | skipped | Intentionally bypassed (stall recovery) |
| pending | - | Not yet started |
| in_progress | - | Builder executing |

### Task State Derivation (`lib/tasks.py`)

```python
helix_task_state(task)
# Returns: {
#   "executable": bool,      # pending and unblocked
#   "finished": bool,        # status=completed
#   "successful": bool,      # finished AND helix_outcome=delivered
#   "outcome": str,          # delivered|blocked|skipped|pending|in_progress
#   "blocks_dependents": bool # finished AND not delivered
# }
```

### DAG Utilities (`lib/dag_utils.py`)

```python
detect_cycles(dependencies)     # → List of cycles found
get_completed_task_ids(tasks)   # → IDs with helix_outcome="delivered"
get_blocked_task_ids(tasks)     # → IDs with helix_outcome="blocked"
get_ready_tasks(tasks)          # → IDs ready for execution
check_stalled(tasks)            # → (is_stalled, stall_info)
clear_checkpoints()             # → Clear all checkpoints
```

## Automatic Feedback Attribution

Hooks create a closed learning loop:

1. **PreToolUse(Task)**: Inject memories, store injection state
2. **Agent executes**: Uses enriched context
3. **Builder reports**: TaskUpdate with `helix_outcome`
4. **PostToolUse(TaskUpdate)**: Auto-credit/debit based on outcome

**Feedback deltas:**
| Outcome | Delta | Effect |
|---------|-------|--------|
| delivered | +0.5 | Increases `helped` |
| blocked | -0.3 | Increases `failed` |

**Override:** Call `feedback` directly with custom delta to override automatic attribution.

## Database Schema

SQLite database at `.helix/helix.db` (WAL mode, write lock for safe writes):

```sql
-- Schema versioning
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Memories: learned failures, patterns, facts, conventions, decisions, evolution
CREATE TABLE memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL,                -- failure, pattern, systemic, fact, convention, decision, evolution
    trigger TEXT NOT NULL,
    resolution TEXT NOT NULL,
    helped REAL DEFAULT 0,
    failed REAL DEFAULT 0,
    embedding BLOB,                    -- 384-dim all-MiniLM-L6-v2
    source TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    last_used TEXT
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

## CLI Reference

### Memory Operations

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..." --source "..."

# Recall (with graph expansion)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Recall grouped by type
python3 "$HELIX/lib/memory/core.py" recall-by-type "query" --types "fact,convention" --limit 5

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

### Observer Operations

```bash
# Extract facts from explorer output
python3 "$HELIX/lib/observer.py" explorer --output '{...}' --store --min-confidence medium

# Extract decisions from planner
python3 "$HELIX/lib/observer.py" planner --tasks '[...]' --exploration '{...}' --store

# Extract evolution/conventions from builder
python3 "$HELIX/lib/observer.py" builder --task '{...}' --result '{...}' --files-changed '[...]' --store

# Create session summary
python3 "$HELIX/lib/observer.py" session --objective "..." --tasks '[...]' --outcomes '{...}' --store
```

### Context Operations

```bash
# Explorer context
python3 "$HELIX/lib/context.py" build-explorer-context --objective "..." --scope "src/api"

# Planner context
python3 "$HELIX/lib/context.py" build-planner-context --objective "..."

# Builder context
python3 "$HELIX/lib/context.py" build-context --task-data '{...}' --lineage '[...]'

# Build lineage from completed tasks
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[...]'
```

### Task Operations

```bash
# Derive task state
python3 "$HELIX/lib/tasks.py" task-state '{"status": "completed", "metadata": {"helix_outcome": "delivered"}}'
```

### DAG Operations

```bash
# Clear checkpoints
python3 "$HELIX/lib/dag_utils.py" clear

# Detect cycles
python3 "$HELIX/lib/dag_utils.py" detect-cycles --dependencies '{"task-002": ["task-001"]}'

# Check stalled
python3 "$HELIX/lib/dag_utils.py" check-stalled --tasks '[...]'
```

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: explore → plan → build → observe |
| `/helix-query <text>` | Search memory by meaning (with graph expansion) |
| `/helix-stats` | Memory health metrics |

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `HELIX_DB_PATH` | Custom database location | `.helix/helix.db` |
| `HELIX_PLUGIN_ROOT` | Plugin root path | Read from `.helix/plugin_root` |
| `HELIX_EMBEDDING_CACHE` | Embedding cache size | 2000 |

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `DECAY_HALF_LIFE_DAYS` | 7 (default) | Base recency score half-life |
| `DUPLICATE_THRESHOLD` | 0.85 | Semantic deduplication threshold |
| `VALID_TYPES` | failure, pattern, systemic, fact, convention, decision, evolution | Allowed memory types |

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest (v1.0.11)
├── .claude/
│   └── settings.json         # Hook configuration
├── agents/
│   ├── explorer.md           # Parallel reconnaissance (haiku)
│   ├── planner.md            # Task decomposition (opus)
│   └── builder.md            # Task execution (opus)
├── lib/
│   ├── __init__.py           # Version: 2.0.0
│   ├── hooks/                # Hook implementations
│   │   ├── __init__.py
│   │   ├── inject_memory.py  # Memory injection
│   │   └── extract_learning.py # Learning extraction
│   ├── memory/
│   │   ├── __init__.py       # Clean exports
│   │   ├── core.py           # 9 core + 4 maintenance primitives
│   │   └── embeddings.py     # all-MiniLM-L6-v2
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py     # SQLite singleton, WAL, write_lock
│   │   └── schema.py         # Memory, MemoryEdge dataclasses
│   ├── context.py            # Agent-specific context building
│   ├── prompt_parser.py      # Prompt field parsing
│   ├── observer.py           # Learning extraction from agents
│   ├── tasks.py              # Task state derivation
│   ├── dag_utils.py          # Cycle detection, stall detection
│   └── wait.py
├── scripts/
│   ├── hooks/                # Hook shell scripts
│   │   ├── pretool-task.sh
│   │   ├── subagent-stop.sh
│   │   └── posttool-taskupdate.sh
│   ├── setup-env.sh          # SessionStart hook
│   └── init.sh               # Database initialization
├── skills/
│   ├── helix/
│   │   ├── SKILL.md          # Main orchestrator
│   │   └── reference/        # Decision tables
│   │       ├── feedback-deltas.md
│   │       ├── edge-creation.md
│   │       ├── stalled-recovery.md
│   │       ├── task-granularity.md
│   │       └── cli-reference.md
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
├── tests/
│   ├── conftest.py
│   ├── test_memory_core.py
│   ├── test_context.py
│   ├── test_tasks.py
│   ├── test_dag_utils.py
│   ├── test_observer.py
│   ├── test_inject_memory.py
│   ├── test_extract_learning.py
│   ├── test_prompt_parser.py
│   └── test_integration.py
└── .helix/                   # Runtime (created on first use)
    ├── helix.db              # SQLite database
    ├── plugin_root           # Plugin path for sub-agents
    ├── injection-state/      # Injection tracking
    └── learning-queue/       # Learning candidates
```

## What Helix Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user collaboration tool (single-user, local SQLite)
- A model-agnostic framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
