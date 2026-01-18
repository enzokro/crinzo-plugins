# ftl

A Claude Code orchestrator that builds knowledge over time.


## Introduction

Before Opus 4.5, agentic harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`ftl` is built on this shift. While previous harnesses constrained models to prevent drift, `ftl` persists knowledge across sessions to build on what we've already done instead of always starting from an empty context window.

## Philosophy

| Principle               | Meaning                                                           |
| ----------------------- | ----------------------------------------------------------------- |
| **Memory compounds**    | Each task leaves the system smarter                               |
| **Verify first**        | Shape work by starting with proof-of-success                      |
| **Bounded scope**       | Workspace files are explicit so humans can audit agent boundaries |
| **Present over future** | Implement current requests, not anticipated needs                 |
| **Edit over create**    | Modify what exists before creating something new                  |
| **Blocking is success** | Informed handoff creates learning data, prevents budget waste     |

These aren't new. In fact, they read like the 101s of good software development. But anyone who's worked with coding agents knows that the models like to work and stay busy. Every part of `ftl` is built around these principles to turn them into the orchestrator's north star.

## Quick Start

```bash
# Add the crinzo-plugins marketplace
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install ftl
claude plugin install ftl@crinzo-plugins
```

Or from inside of Claude Code:
```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install ftl@crinzo-plugins
```

## Development Loop

```
/ftl <task>
    │
    ▼
┌─────────────────────────────────────┐
│  EXPLORER (4x parallel)             │
│  structure │ pattern │ memory │ delta
└─────────────────────────────────────┘
    │
    ▼ exploration (database)
┌─────────────────────────────────────┐
│  PLANNER                            │
│  Decompose → Verify → Budget → Order│
└─────────────────────────────────────┘
    │
    ▼ plan.json (DAG with dependencies)
┌─────────────────────────────────────┐
│  BUILDER (parallel where possible)  │
│  Read spec → Implement → Verify     │
└─────────────────────────────────────┘
    │
    ▼ complete/blocked workspaces (database)
┌─────────────────────────────────────┐
│  OBSERVER                           │
│  Verify blocks → Extract patterns   │
└─────────────────────────────────────┘
    │
    ▼ memory (database)
```

**Explorers** gather codebase context in parallel. **Planner** decomposes work into a task DAG with dependencies. **Builders** execute tasks in parallel where dependencies allow. **Observer** extracts patterns from outcomes — both successes and failures become future knowledge.

Each completed task makes the system smarter. Patterns emerge over time to influence future work.

## Agents

Four agents with distinct roles:

| Agent | Model | Role | Budget |
|-------|-------|------|--------|
| **Explorer** | Haiku | Parallel codebase reconnaissance (4 modes) | 4 |
| **Planner** | Opus | Decompose objectives into verifiable tasks | — |
| **Builder** | Opus | Transform workspace spec into code | 3-7 |
| **Observer** | Opus | Extract patterns, update memory | 10 |

**Explorer modes** run in parallel:
- **structure**: Maps directories, entry points, test patterns, language
- **pattern**: Detects framework, extracts idioms (required/forbidden)
- **memory**: Retrieves semantically relevant failures and patterns
- **delta**: Identifies candidate files and functions for modification

**Constraints:**
- Explorers write to `explorer_result` table in `.ftl/ftl.db` for session-based aggregation
- Planner validates DAG structure — cyclic dependencies are rejected at registration
- Builder reads test file (`verify_source`) before implementing to match expectations
- Builder enforces framework idioms as non-negotiable — blocks even if tests pass
- Multi-file tasks get code context for all delta files, not just the first
- Blocked sibling tasks inject failures into subsequent workspaces (intra-campaign learning)
- Observer verifies blocked workspaces before extracting failures (prevents false positives)
- Blocking is success — informed handoff, not failure

**Shared References**: Agents share common specifications via `agents/shared/`:
- `ONTOLOGY.md` — Canonical definitions (budget, BLOCK status, framework confidence)
- `BUILDER_STATE_MACHINE.md` — 10-state builder FSM with transitions
- `PLANNER_PHASES.md` — 8-phase planning flow
- `EXPLORER_SCHEMAS.md` — JSON output schemas for 4 explorer modes
- `CONSTRAINT_TIERS.md` — Essential/Quality tiers with per-agent constraints
- `FRAMEWORK_IDIOMS.md` — Detection rules and idiom requirements
- `TOOL_BUDGET_REFERENCE.md` — Budget counting rules and exemptions
- `ERROR_MATCHING_RULES.md` — Judgment-based matching with flaky retry guidance
- `OUTPUT_TEMPLATES.md` — Standard output formats

## Commands

| Command | Purpose |
|---------|---------|
| `/ftl <task>` | Full pipeline: explore → plan → build → observe |
| `/ftl campaign "objective"` | Multi-task campaign with DAG parallelization |
| `/ftl query "topic"` | Surface relevant precedent from memory (semantic ranking) |
| `/ftl status` | Current campaign and workspace state |
| `/ftl stats` | Memory health metrics and tier distribution |
| `/ftl prune` | Remove low-importance entries |
| `/ftl related "name"` | Graph traversal from an entry |
| `/ftl similar` | Find similar past campaigns |
| `/ftl observe` | Run automated analysis pipeline |
| `/ftl benchmark` | Performance metrics report |

## Workspace Format

Tasks produce workspace records in the `workspace` table of `.ftl/ftl.db`. Each workspace is a contract between planner and builder — what to do, how to verify, and what to watch out for.

**Database Schema:**

```sql
CREATE TABLE workspace (
    id INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL UNIQUE,  -- "001-slug" format
    campaign_id INTEGER NOT NULL,       -- FK → campaign.id
    seq TEXT NOT NULL,
    slug TEXT NOT NULL,
    status TEXT DEFAULT 'active',       -- "active" | "complete" | "blocked"
    created_at TEXT NOT NULL,
    completed_at TEXT,
    blocked_at TEXT,
    objective TEXT,
    delta TEXT DEFAULT '[]',            -- JSON: files to modify
    verify TEXT,
    verify_source TEXT,
    budget INTEGER DEFAULT 5,
    framework TEXT,
    framework_confidence REAL DEFAULT 1.0,
    idioms TEXT DEFAULT '{}',           -- JSON: {required, forbidden}
    prior_knowledge TEXT DEFAULT '{}',  -- JSON: injected memories
    lineage TEXT DEFAULT '{}',          -- JSON: parent references
    delivered TEXT,
    utilized_memories TEXT DEFAULT '[]', -- JSON: feedback tracking
    code_contexts TEXT DEFAULT '[]',    -- JSON: code snapshots
    preflight TEXT DEFAULT '[]'         -- JSON: preflight checks
);
```

**Virtual Path Compatibility:**

For CLI compatibility, `workspace.py` returns `Path`-like strings that map to database records:

```python
# workspace.create() returns virtual paths
paths = workspace.create(plan, task_seq="001")
# → [Path(".ftl/workspace/001-task-slug")]

# These paths resolve to database lookups internally
workspace.complete(path, delivered="Task done")  # Updates workspace table
```

**Naming:** `{SEQ}-{slug}` format stored in `workspace_id` column
- `SEQ` — 3-digit sequence (001, 002, 003)
- `status` — tracked in `status` column: `active`, `complete`, or `blocked`

**Key fields:**
- `objective` — WHY this task exists (the user's original intent)
- `verify_source` — Test file to read before implementing
- `lineage` — JSON object with parent references and deliveries (supports multiple parents for DAG convergence)

**ACID Transactions**: All workspace operations use SQLite transactions for crash safety.

The workspace is the builder's single source of truth. Framework idioms are non-negotiable. If something goes wrong that isn't in prior knowledge, the builder blocks — discovery is needed, not more debugging.

## Memory

A unified system capturing what went wrong and what worked:

| Storage | Purpose |
|---------|---------|
| `.ftl/ftl.db` | SQLite database containing all persistent state |
| `memory` table | Failures and patterns with semantic retrieval |
| `campaign` table | Active campaign state with DAG |
| `workspace` table | Workspace execution records |
| `exploration` table | Aggregated explorer outputs |
| `archive` table | Completed campaign archives |

**Capacity**: 500 failures + 200 patterns (~130KB estimated storage)

**Failures** — Observable errors with executable fixes. Each failure includes: a trigger (the error message), a fix (the action that resolves it), a regex match pattern (to catch in logs), and a cost estimate. Injected into builder's `prior_knowledge` to prevent repeats.

**Patterns** — Reusable approaches that saved significant tokens. High bar: non-obvious insights a senior dev would appreciate. Scored on: blocked→fixed (+3), idiom applied (+2), multi-file (+1), novel approach (+1). Scores are **heuristic guidance** — extract when the workspace demonstrates a transferable technique, skip high scores that succeeded by luck.

### Embedding-Based Retrieval

Memory uses 384-dimensional embeddings (`all-MiniLM-L6-v2` model) for semantic similarity matching. Embeddings are stored as BLOBs (1,536 bytes each: 384 floats × 4 bytes) in the `memory` and `campaign` tables.

### Hybrid Scoring

When retrieving context, memories are scored by a hybrid formula:

```
score = relevance × log₂(cost + 1)
```

This balances "how relevant is this to my current task?" with "how expensive was this to discover?" — ensuring you don't repeat expensive mistakes while avoiding irrelevant-but-costly noise.

**Comparison to alternatives:**
- Mem0: Triplet ranking (separate relevance/value)
- MAGMA: 4 orthogonal graphs (temporal/causal/entity/semantic)
- FTL: Single integrated formula

### Tiered Injection (Based on Agent judgement)

Memories are classified into injection tiers. Similarity scores are **guidance, not gates**:

| Tier | Typical Range | Guidance |
|------|---------------|----------|
| **Critical** | ~0.6+ | Strong candidates for injection |
| **Productive** | ~0.4-0.6 | Evaluate based on task complexity |
| **Exploration** | ~0.25-0.4 | Consider for novel/complex work |
| **Archive** | <0.25 | Rarely relevant |

**Override automation when:**
- High similarity but tangential relevance → skip
- Lower similarity but obviously applicable → inject
- Complex task needing more context → include productive tier
- Simple task → critical tier only

Select prior knowledge based on task complexity, track record (helped/failed ratio), and contextual relevance — semantic similarity is one signal, not the only signal.

### Deduplication

85% semantic similarity threshold prevents near-duplicate entries. Sources are merged when duplicates detected.

### Memory Feedback Loop

Memories that help persist longer; memories that don't decay faster:

```python
# Builder reports which memories were actually used
complete(..., utilized_memories=["import-error", "jwt-refresh"])

# Observer records feedback
record_feedback("import-error", "failure", helped=True)   # → 1.5× persistence
record_feedback("jwt-refresh", "pattern", helped=False)   # → 0.5× decay
```

Importance scoring combines multiple factors:

```
importance = log₂(value + 1) × age_decay × access_boost × effectiveness × exploration_bonus

where:
  age_decay = 0.5^(age_days / 30)           # 30-day half-life
  access_boost = 1 + 0.05 × √(access_count) # Diminishing returns
  effectiveness = 0.5 + (helped / total)     # [0.5, 1.5] range
  exploration_bonus = 1.1 if age < 7 days    # Encourage discovery
```

### Graph Relationships

Failures and patterns can be linked with typed, weighted edges:

```bash
python3 lib/memory.py add-relationship auth-timeout database-connection --type failure

# Later retrieval with multi-hop traversal
python3 lib/memory.py related auth-timeout --max-hops 2
# Returns: database-connection (1 hop), connection-retry (2 hops)
```

**Relationship types:**
| Type | Weight | Meaning |
|------|--------|---------|
| `solves` | 1.5 | Pattern fixes failure |
| `causes` | 1.0 | A leads to B |
| `prerequisite` | 1.0 | Must understand A before B |
| `co_occurs` | 0.8 | Correlation, not causation |
| `variant` | 0.7 | Similar but different |

**Path pruning**: Weak transitive chains (weight product < 0.5) are pruned.

This enables discovery across related issues: "I'm seeing auth timeouts — what caused those, and what fixed the cause?"

### Pruning

Memory self-manages through importance-based pruning:

```bash
python3 lib/memory.py prune --max-failures 500 --max-patterns 200 --min-importance 0.1
```

Low-importance entries (old, unused, ineffective) are pruned first. The system maintains bounded size while preserving high-value knowledge.

### Health Metrics

```bash
python3 lib/memory.py stats
```

Returns:
- Capacity utilization
- Average importance scores
- Stale ratio (>90 days, never accessed)
- Untested ratio (no feedback)
- Tier distribution
- Graph connectivity

## Database Architecture

All persistent state is stored in `.ftl/ftl.db` (SQLite via fastsql). The schema consists of 11 tables:

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `memory` | Failures/patterns with 384-dim embeddings | `name`, `type`, `trigger`, `resolution`, `embedding` |
| `memory_edge` | Graph relationships for BFS traversal | `from_id`, `to_id`, `rel_type`, `weight` |
| `campaign` | Campaign state with embedded task DAG | `objective`, `tasks` (JSON), `status`, `fingerprint` |
| `workspace` | Execution records (replaces XML files) | `workspace_id`, `objective`, `delta`, `lineage` |
| `archive` | Completed campaign index for similarity | `objective_embedding`, `fingerprint`, `outcome` |
| `exploration` | Aggregated explorer outputs | `structure`, `pattern`, `memory`, `delta` (JSON each) |
| `explorer_result` | Session-based explorer staging | `session_id`, `mode`, `result`, `status` |
| `plan` | Stored task plans | `tasks` (JSON), `idioms`, `status` |
| `phase_state` | Workflow phase tracking (singleton) | `phase`, `transitions` (JSON) |
| `event` | Append-only audit log | `event_type`, `timestamp`, `metadata` |
| `benchmark` | Performance metrics | `run_id`, `metric`, `value` |

### Session-Based Explorer Coordination

Parallel explorers write to `explorer_result` with a shared `session_id`:

```python
# Orchestrator creates session
session_id = orchestration.create_session()["session_id"]

# 4 explorers run in parallel, each writes to explorer_result
# mode ∈ {structure, pattern, memory, delta}

# Quorum detection
wait_result = orchestration.wait_explorers(session_id, required=3, timeout=300)
# Returns: "all_complete" | "quorum_met" | "timeout" | "quorum_failure"

# Aggregate into exploration table
exploration.aggregate_session(session_id, objective)
```

### Virtual Path Compatibility

For backward compatibility with Path-based APIs, `workspace.py` provides virtual paths that map to database records:

```
Path(".ftl/workspace/001-task-slug")  →  workspace_id="001-task-slug" in DB
```

The `workspace.create()`, `workspace.complete()`, and `workspace.block()` functions accept and return `Path` objects while storing data in SQLite.

## DAG Execution

Campaigns support multi-parent task dependencies:

```json
{
  "tasks": [
    {"seq": "001", "slug": "spec-auth", "depends": "none"},
    {"seq": "002", "slug": "spec-api", "depends": "none"},
    {"seq": "003", "slug": "impl-auth", "depends": "001"},
    {"seq": "004", "slug": "impl-api", "depends": "002"},
    {"seq": "005", "slug": "integrate", "depends": ["003", "004"]}
  ]
}
```

```
001 (spec-auth) ──→ 003 (impl-auth) ──┐
                                      ├──→ 005 (integrate)
002 (spec-api) ──→ 004 (impl-api) ───┘
```

**Parallel execution**: Tasks with no dependencies or all dependencies complete can run simultaneously. Independent branches (001→003 and 002→004) execute in parallel.

### Cycle Detection

Dependencies are validated at registration using DFS:

```
Algorithm: detect_cycles(tasks)
  1. Build adjacency list from task.depends
  2. For each task: DFS with recursion_stack
  3. If task in recursion_stack → CYCLE DETECTED
  4. Return: has_cycle, cycle_path
```

Cyclic graphs are rejected with a clear error showing the cycle path.

### Cascade Handling

When a parent task blocks, child tasks become unreachable:

```
Algorithm: cascade_status(campaign)
  1. Get all blocked tasks → blocked_set
  2. For each pending task:
     - If ANY depends in blocked_set → unreachable
  3. Return: {state: "stuck" | "progressing", unreachable: [...]}
```

The orchestrator detects stuck campaigns. When ≥2 tasks become unreachable, **adaptive re-planning** triggers:

1. `get-replan-input` collects completed work, blocked reasons, and pending tasks
2. Planner generates revised plan with alternative paths around blockers
3. `merge-revised-plan` updates dependencies without losing completed work
4. Campaign resumes from EXECUTE state with revised DAG

If re-planning isn't viable, blocks propagate to unreachable tasks with `blocked_by` references. Campaigns complete gracefully with partial success rather than hanging indefinitely.

### Sibling Failure Injection

When a task blocks, its failure is injected into subsequent tasks *at workspace creation time*:

| Event | What Happens |
|-------|--------------|
| Plan created | Tasks defined, no workspaces yet |
| Task 001 starts | Workspace with memory.get_context() only |
| Task 001 blocks | Status updated to `blocked` in workspace table |
| Task 002 starts | Workspace with memory + sibling failures |

```json
{
  "prior_knowledge": {
    "failures": [
      {
        "name": "sibling-001_auth-impl",
        "trigger": "ImportError: fasthtml.core not found",
        "fix": "See blocked workspace for attempted fixes",
        "injected": false
      }
    ]
  }
}
```

**Why at creation time, not planning?** The planner runs once BEFORE any building. Sibling failures only exist AFTER builders encounter them. Dynamic injection ensures freshness.

### Campaign Fingerprinting

Similar past campaigns are discovered through semantic fingerprinting:

```bash
python3 lib/campaign.py find-similar --threshold 0.5 --max 3
```

Returns campaigns with similar objectives, framework, and delta patterns — providing context on what worked (and what didn't) for comparable requests.

## CLI Tools

The `lib/` directory provides Python utilities for orchestration. All data stored in `.ftl/ftl.db` SQLite database:

| Library | Purpose | Key Commands |
|---------|---------|--------------|
| `exploration.py` | Aggregate explorer outputs | `aggregate-files`, `read`, `write`, `clear` |
| `campaign.py` | Campaign lifecycle and DAG | `create`, `add-tasks`, `ready-tasks`, `cascade-status`, `propagate-blocks`, `complete`, `find-similar`, `get-replan-input`, `merge-revised-plan` |
| `workspace.py` | Task workspace management | `create`, `complete`, `block`, `parse`, `list` |
| `memory.py` | Pattern/failure storage | `context`, `add-failure`, `add-pattern`, `query`, `prune`, `feedback`, `add-relationship`, `related`, `stats`, `add-cross-relationship`, `get-solutions` |
| `observer.py` | Automated extraction | `analyze`, `extract-failure`, `verify-blocks` |
| `phase.py` | State transitions | O(1) dispatch |
| `db/` | Database schema and connection | fastsql-based SQLite storage |

**Adaptive Re-Planning:** `get-replan-input` generates context when campaigns get stuck. `merge-revised-plan` integrates revised task dependencies without losing completed work.

**DAG Scheduling:** `ready-tasks` returns all tasks whose dependencies are complete, enabling parallel execution. `cascade-status` detects stuck campaigns. `propagate-blocks` marks unreachable tasks.

**Semantic Memory:** `context --objective "text"` retrieves memories ranked by semantic relevance. `query "topic"` searches with semantic ranking.

**Concurrency:** All database operations use SQLite transactions for ACID compliance. Explorer sessions use `session_id` for quorum coordination.

## Examples

### Single Task: API Endpoint with Tests

```bash
/ftl add CRUD endpoints for user profiles with validation
```

**What happens:**
1. **Explorers** (parallel): Map codebase structure, detect FastAPI framework + Pydantic idioms, retrieve 3 similar past failures, identify `routes/users.py` as delta target
2. **Planner**: Produces 2-task DAG — `001_spec-tests` (write test stubs) → `002_impl-routes` (implement to pass tests)
3. **Builder 001**: Creates `test_users.py` with validation edge cases; completes
4. **Builder 002**: Implements routes; first attempt fails validation; matches `pydantic-field-validator` from prior_knowledge; retries with fix; completes
5. **Observer**: Extracts pattern "validator-before-model" (blocked→fixed recovery); updates memory

### Multi-Task Campaign: Feature Branch

```bash
/ftl campaign "add real-time notifications with WebSocket support and Redis pub/sub"
```

**What happens:**
```
001 (spec-ws-protocol)  ──→ 003 (impl-ws-handler) ──┐
                                                    ├──→ 005 (integrate-notifications)
002 (spec-redis-pubsub) ──→ 004 (impl-redis-client) ┘
```

- Tasks 001 and 002 run **in parallel** (no dependencies)
- Task 003 waits for 001; Task 004 waits for 002
- Task 005 waits for **both** 003 and 004 (DAG convergence)
- If 003 blocks, 005 becomes unreachable → **adaptive re-planning** triggers:
  - Planner receives blocked context + completed work
  - Generates revised plan with alternative path (e.g., polling fallback)
  - Campaign continues with merged plan

### Learning Across Sessions

```bash
# Session 1: First FastHTML project
/ftl campaign "build a todo app with FastHTML"
# Builder blocks on: "TypeError: FT objects don't support + concatenation"
# Observer extracts failure with fix: "Use Div(*children) not Div() + child"

# Session 2: Different FastHTML project, weeks later
/ftl add a comment section component
# Explorer retrieves the FT concatenation failure (semantic match)
# Builder avoids the mistake entirely — prior_knowledge injection worked
```

### Recovery from Flaky Tests

```bash
/ftl add integration tests for payment webhook
# First attempt: timeout on Stripe sandbox
# Builder recognizes flaky indicator → allows 2 retries (judgment-based)
# Second attempt: succeeds
# Observer notes "stripe-webhook-timeout" with flaky tag for future reference
```

### Diagnostic Commands

```bash
# Semantic search across all learned patterns
/ftl query "authentication token refresh"

# Campaign health and DAG state
/ftl status

# Memory statistics: tier distribution, stale ratio, effectiveness
/ftl stats

# Find campaigns similar to current objective (transfer learning)
/ftl similar

# Graph traversal: what's related to a specific failure?
/ftl related "database-connection-pool"
```

## What's Automated vs. What's Documented

FTL operates on two layers:

| Layer | How It Works | Reliability |
|-------|--------------|-------------|
| **Python Infrastructure** | Deterministic code | Guaranteed |
| **Agent Instructions** | Claude following markdown specs | Probabilistic |

**Automated (100% reliable):**
- Semantic memory retrieval and hybrid scoring
- Bloom filter duplicate detection
- Tiered injection classification
- DAG scheduling and cycle detection
- Cascade handling for blocked parents
- Sibling failure injection at workspace creation
- **Mid-campaign learning injection** (PostToolUse hook extracts failures immediately on block)
- Block verification in Observer
- Pattern/failure deduplication (85% threshold)
- Memory feedback recording
- SQLite transactions for ACID compliance
- Session-based explorer coordination (quorum detection)
- Pruning based on importance scores
- Graph relationship traversal with weight pruning
- **Adaptive re-planning** trigger when ≥2 tasks unreachable

**Documented (agent judgment):**
- Cross-workspace synthesis and relationship discovery
- Idiom compliance checking (Builder follows spec)
- Pattern extraction decision (scores are guidance, not gates)
- Error match determination (similarity + applicability)
- Retry count for flaky vs deterministic errors
- Memory injection tier selection based on task complexity
- Override of false positives in Observer
- CLARIFY decision gate in Planner

The automated layer provides reliable intra-campaign learning. The instruction layer documents best practices for agents to follow — more powerful than pure automation for complex synthesis, but dependent on agent judgment.


## When to Use

**Use ftl when:**
- Work should persist as precedent and compound over time
- You want bounded, reviewable scope
- Knowledge should build and evolve over sessions
- Complex objectives need coordination across multiple tasks
- Framework-specific development (FastHTML, FastAPI) with idiom enforcement
- Repetitive patterns where past failures inform future work

**Skip ftl when:**
- Exploratory prototyping where you want the models to wander
- Quick one-offs with no future value
- Simple queries you'd ask Claude directly
- Team collaboration (single-user design)
- Novel frameworks without idiom definitions

## Architecture

| Module | Purpose | Status |
|--------|---------|--------|
| `lib/memory.py` | Semantic memory with Bloom filter, decay, pruning, graph | Production |
| `lib/campaign.py` | DAG scheduling, cycle detection, cascade handling, fingerprinting | Production |
| `lib/workspace.py` | Workspace lifecycle, lineage, sibling injection (database-backed) | Production |
| `lib/observer.py` | Parallelized pattern/failure extraction | Production |
| `lib/exploration.py` | Multi-mode aggregation with similar campaigns | Production |
| `lib/phase.py` | O(1) state transitions | Production |
| `lib/orchestration.py` | Explorer quorum management, state emission | Production |
| `lib/benchmark.py` | Performance metrics and learning simulation | Production |
| `lib/db/` | SQLite schema, connection, embeddings (fastsql) | Production |
| `agents/explorer.md` | 4-mode exploration spec | — |
| `agents/planner.md` | Task decomposition spec | — |
| `agents/builder.md` | Implementation FSM spec | — |
| `agents/observer.md` | Learning extraction spec | — |
| `agents/shared/` | Consolidated reference docs (9 files) | — |

## What FTL Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user or team collaboration tool (single-user, local SQLite)
- A model-agnostic orchestration framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
- A replacement for Mem0/Graphiti (complementary, not competing)
