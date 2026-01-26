# helix

A Claude Code orchestrator with integrated memory. helix persists useful, important knowledge across sessions to build on your work over time.

## Introduction

Before Opus 4.5, agentic harnesses focused on working around the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. We are now living the transformation of LLM agents from spastic assistants to capable collaborators.

These previous harnesses quickly became bloated as they tried to keep the models from drifting and added many features to close model capability gaps. helix instead builds on the meaningful agentic jump in Opus 4.5 and removes these low level training wheels and hand-holding. 


## Philosophy

| Principle | Meaning |
|-----------|---------|
| Feedback closes the loop | Every task completion updates memory effectiveness |
| Verify first | Shape work by starting with proof-of-success |
| Bounded scope | Relevant files are explicit so humans can audit agent boundaries |
| Present over future | Implement current requests, not anticipated needs |
| Edit over create | Modify what exists before creating something new |
| Blocking is success | Informed handoff creates learning data, prevents budget waste |

## Architecture

```
helix/
├── .claude-plugin/
│   └── plugin.json             # Hook registration, plugin metadata
├── scripts/
│   ├── setup-env.sh            # SessionStart: venv, deps, DB init
│   └── init.sh                 # Database initialization
├── lib/
│   ├── __init__.py             # Version: 2.0.0
│   ├── memory/
│   │   ├── core.py             # 9 core + 2 code-assisted primitives
│   │   └── embeddings.py       # all-MiniLM-L6-v2, fallback logic
│   ├── db/
│   │   ├── connection.py       # SQLite singleton, WAL, write_lock
│   │   └── schema.py           # Memory, MemoryEdge dataclasses
│   ├── context.py              # Builder prompt construction, dual-query memory retrieval
│   ├── tasks.py                # Output parsing, task state derivation
│   └── dag_utils.py            # Cycle detection, ready task calculation, stall detection
├── skills/
│   ├── helix/SKILL.md          # Main orchestrator
│   ├── helix/reference/        # Decision tables (feedback, edges, stall recovery, etc.)
│   ├── helix-query/SKILL.md    # Memory search
│   └── helix-stats/SKILL.md    # Health check
├── agents/
│   └── *.md                    # Agent definitions (explorer, planner, builder)
└── .helix/                     # Runtime data (created on first use)
    ├── helix.db                # SQLite database
    └── plugin_root             # Cached plugin path for sub-agents
```

**Prose-driven orchestrator**: SKILL.md holds the orchestration logic that fully leverages Opus 4.5's capabilities. The Python utilities help guide the orchestration. We also integrate the new Task tool to keep state in the conversation itself. The single source of state truth is the TaskList's metadata.

**Memory** (lib/memory/core.py) provides semantic storage with effectiveness tracking and graph relationships. Memories are stored in a local SQLite database at `.helix/helix.db`.

**Three agents** are specialized for their phase: Explorer (Haiku) for quickly learning about the project's landscape. Planner and Builder inherit from Opus for their complex reasoning. The orchestrator looks at the agent's process and extract meaningful, helpful memories for the future.

## Quick Start

```bash
# Add the crinzo-plugins marketplace
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install helix
claude plugin install helix@crinzo-plugins
```

Or from inside Claude Code:
```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install helix@crinzo-plugins
```

## Why Helix?

**Feedback closes the loop.** Memory layers store and retrieve; helix closes the loop. Every memory gets a helped/failed ratio updated based on verification outcomes. Memories that work rise in ranking; memories that don't sink. The system gets smarter through use, not just accumulation.

**Bounded execution.** Three agents with explicit roles. When a builder hits an unknown error, it blocks—creating learning data rather than burning tokens. Relevant files are guidance, not hard constraints. You always know what the agent is working on.

**Local-first.** SQLite database in `.helix/helix.db`. Your failures, patterns, and systemic issues stay on your machine. No API keys for memory services, no usage fees, no data leaving your system.

**Unified architecture.** Memory and orchestration are one system. Direct Python imports, not subprocess calls. The feedback loop closes within a single function call. No external plugin discovery, no silent degradation.

## Development Loop

```
/helix <task>
    │
    ▼
┌─────────────────────────────────────────────┐
│  EXPLORER SWARM (haiku)                     │
│  Tools: Read, Grep, Glob, Bash              │
│  Parallel reconnaissance by scope           │
└─────────────────────────────────────────────┘
    │
    ▼ merged exploration
┌─────────────────────────────────────────────┐
│  PLANNER (opus)                             │
│  Tools: Read, Grep, Glob, Bash,             │
│         TaskCreate, TaskUpdate              │
│  Decompose → Dependencies → Verify          │
└─────────────────────────────────────────────┘
    │
    ▼ task DAG (native TaskList)
┌─────────────────────────────────────────────┐
│  BUILDER(S) (opus, parallel)                │
│  Tools: Read, Write, Edit, Grep, Glob,      │
│         Bash, TaskUpdate                    │
│  Read → Implement → Verify → Report         │
└─────────────────────────────────────────────┘
    │
    ▼ DELIVERED/BLOCKED + verification
┌─────────────────────────────────────────────┐
│  ORCHESTRATOR JUDGMENT                      │
│  Feedback, edge creation, systemic detection│
│  Learning extraction (store/skip decision)  │
└─────────────────────────────────────────────┘
```

**Explorer swarm** (Haiku) runs in parallel—one agent per scope. Gathers structure, framework patterns, and relevant memories. Orchestrator merges findings.

**Planner** (Opus) decomposes work into a task DAG with dependencies and verification commands. Registers tasks in Claude Code's native Task system (visible via Ctrl+T).

**Builders** (Opus) execute tasks. Block on unknown errors rather than debugging indefinitely. Report DELIVERED or BLOCKED. Multiple builders run in parallel when dependencies allow.

**Orchestrator judgment** closes the feedback loop. Decides delta weights, creates graph edges, detects systemic patterns (3+ occurrences), and determines what to learn vs. skip.

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <task>` | Full pipeline: explore → plan → build → observe |
| `/helix-query "topic"` | Surface relevant precedent from memory |
| `/helix-stats` | Memory health metrics |

## Memory System

Three memory types: **failure** (what went wrong), **pattern** (successful approaches), **systemic** (recurring issues, 3+ occurrences). Stored with 384-dimensional embeddings via `all-MiniLM-L6-v2`.

**9 core primitives**: store, recall, get, edge, edges, feedback, decay, prune, health.
**2 code-assisted functions**: similar-recent (systemic detection), suggest-edges (graph expansion candidates).

**Scoring formula** balances relevance, effectiveness, and recency:

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)
```

Where:
- `effectiveness = helped / (helped + failed)` — default 0.5 if no feedback
- `recency = 2^(-days_since_use / 7)` — ACT-R decay, 7-day half-life

**Feedback loop**: Verification outcomes drive memory effectiveness. Pass → partial credit to injected memories. Fail → no penalty (unknown cause). Memories that consistently help rise in ranking; ineffective ones decay.

**Graph relationships** link memories (solves, co_occurs, similar, causes). Recall with `--expand` traverses 1-hop neighbors.

**Dual-query strategy**: Context builder queries both semantically (on objective) and by file patterns (on relevant files), then merges and dedupes.

### Database Schema

SQLite database at `.helix/helix.db` (WAL mode for concurrent access):

```sql
schema_version (version, applied_at)
memory (id, name, type, trigger, resolution, helped, failed, embedding, source, created_at, last_used, file_patterns)
memory_edge (id, from_name, to_name, rel_type, weight, created_at)
memory_file_pattern (memory_name, pattern)  -- Normalized for fast lookup
```

### CLI Reference (9 Core + 2 Code-Assisted)

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."

# Recall (with graph expansion)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Get single memory
python3 "$HELIX/lib/memory/core.py" get "memory-name"

# Create edge
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves

# Query edges
python3 "$HELIX/lib/memory/core.py" edges --name "memory-name"

# Feedback (delta: positive for helped, negative for failed)
python3 "$HELIX/lib/memory/core.py" feedback --names '["mem1", "mem2"]' --delta 0.5

# Decay dormant memories
python3 "$HELIX/lib/memory/core.py" decay --days 30 --min-uses 2

# Prune ineffective memories
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Health check
python3 "$HELIX/lib/memory/core.py" health

# Code-assisted (surfaces facts, I decide)
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
```

### Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| DECAY_HALF_LIFE_DAYS | 7 | Recency score half-life |
| DUPLICATE_THRESHOLD | 0.85 | Semantic deduplication threshold |
| SCORE_WEIGHTS | 0.5/0.3/0.2 | Relevance/effectiveness/recency |
| VALID_TYPES | failure, pattern, systemic | Allowed memory types |

### Optional Dependencies

Embeddings require `sentence-transformers` and `numpy`. If unavailable, memory falls back to effectiveness-only ranking (no semantic search). Install via:

```bash
pip install sentence-transformers numpy
```

See [HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md) for technical reference.

## Task DAG

Plans support task dependencies with verification at each step:

```
001 (spec-auth) ──→ 003 (impl-auth) ──┐
                                      ├──→ 005 (integrate)
002 (spec-api) ──→ 004 (impl-api) ───┘
```

Each task has:
- `delta` — files the builder may modify (hard constraint)
- `verify` — command to verify completion
- `depends` — tasks that must complete first

Builders cannot modify files outside their delta. Verification must pass before claiming DELIVERED.

## Native Task Integration

Tasks created by the Planner are visible in Claude Code's native task system (Ctrl+T). This provides:

- **Visibility**: See task progress without reading agent output
- **Ownership**: Tasks have `owner` field for claim tracking
- **Dependencies**: `blockedBy` prevents starting before prerequisites complete
- **Parallel execution**: Multiple builders via `run_in_background: true`

The Planner uses `TaskCreate` to register tasks; Builders use `TaskUpdate` to report progress and completion.

## Hook System

Hooks provide environment setup for helix sessions.

### SessionStart Hook

`scripts/setup-env.sh` runs when a session begins:
1. Creates Python venv if needed
2. Installs dependencies (sentence-transformers, numpy)
3. Initializes `.helix/helix.db` if missing
4. Persists plugin root to `.helix/plugin_root`
5. Reports memory health status

### Learning Loop Flow

Memory injection happens at context build time, not via hooks:

```
1. Orchestrator calls lib/context.py build-context
2. Context builder queries memory (semantic + file patterns)
3. Memories injected with confidence indicators: [75%] or [unproven]
4. Builder executes with memory context
5. Orchestrator runs verify command
6. Orchestrator calls feedback() with delta based on verification
7. Future recalls rank by actual effectiveness
```

The feedback loop is verification-based (incorruptible): builders can't game the system by self-reporting.

## Examples

### Single Task

```bash
/helix add CRUD endpoints for user profiles with validation
```

Explorer swarm maps structure and detects framework. Planner produces task DAG. Builders execute with memory injection. Orchestrator extracts patterns from outcomes.

### Learning Across Sessions

```bash
# Session 1: Builder blocks on circular import error
# Orchestrator extracts failure with fix

# Session 2 (weeks later): Different project
/helix add a notification service
# Explorer retrieves the failure; builder avoids the mistake
```

## When to Use

**Use helix when:**
- Work should persist as precedent
- You want bounded, reviewable scope
- Complex objectives need multi-task coordination
- Framework-specific development with idiom enforcement
- Past failures should inform future work

**Skip helix when:**
- Exploratory prototyping (let models wander)
- Quick one-offs with no future value
- Simple single-file changes
- Novel frameworks without idiom definitions

## Configuration

### Database Path

Default: `.helix/helix.db` in the project root. Override with `HELIX_DB_PATH` environment variable.

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `HELIX_DB_PATH` | Custom database location |
| `HELIX_EMBEDDING_CACHE` | Override embedding cache size (default: 2000) |

### Sub-agent Context

Spawned agents (explorers, builders) need to locate the plugin. The `.helix/plugin_root` file stores the absolute path, created by `setup-env.sh` during session start.

## Documentation

For comprehensive technical reference—agent specifications, database schemas, configuration constants, and CLI tools—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
