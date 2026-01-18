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
    ▼ exploration.json
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
    ▼ complete/blocked workspaces
┌─────────────────────────────────────┐
│  OBSERVER                           │
│  Verify blocks → Extract patterns   │
└─────────────────────────────────────┘
    │
    ▼ memory.json
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
- Explorers write to `.ftl/cache/explorer_{mode}.json` for reliable aggregation
- Planner validates DAG structure — cyclic dependencies are rejected at registration
- Builder reads test file (`verify_source`) before implementing to match expectations
- Builder enforces framework idioms as non-negotiable — blocks even if tests pass
- Multi-file tasks get code context for all delta files, not just the first
- Blocked sibling tasks inject failures into subsequent workspaces (intra-campaign learning)
- Observer verifies blocked workspaces before extracting failures (prevents false positives)
- Blocking is success — informed handoff, not failure

**Shared References**: Agents share common specifications via `agents/shared/`:
- `CONSTRAINT_TIERS.md` — Essential/Quality/Style tiers with per-agent constraints
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

Tasks produce XML workspace files in `.ftl/workspace/`. Each workspace is a contract between planner and builder — what to do, how to verify, and what to watch out for.

```xml
<workspace id="003-routes-crud" status="active">
  <objective>Add CRUD routes for user management</objective>
  <implementation>
    <delta>src/routes.py</delta>
    <verify>pytest routes/test_*.py -v</verify>
    <verify_source>routes/test_crud.py</verify_source>
    <budget>5</budget>
  </implementation>
  <code_context path="src/routes.py" lines="45-120">
    <content>...</content>
    <exports>get_user(), create_user()</exports>
  </code_context>
  <idioms framework="FastHTML">
    <required>use @rt decorator for routes</required>
    <forbidden>raw HTML string construction</forbidden>
  </idioms>
  <prior_knowledge>
    <pattern name="stubs-in-first-build" saved="2293760000">...</pattern>
    <failure name="import-order" cost="2500">...</failure>
  </prior_knowledge>
  <lineage>
    <parent seq="001" workspace="001_spec-routes_complete">
      <prior_delivery>Test stubs created</prior_delivery>
    </parent>
    <parent seq="002" workspace="002_impl-models_complete">
      <prior_delivery>User model implemented</prior_delivery>
    </parent>
  </lineage>
  <delivered></delivered>
</workspace>
```

**Naming:** `NNN_task-slug_status.xml`
- `NNN` — 3-digit sequence (001, 002, 003)
- `status` — `active`, `complete`, or `blocked`

**Key fields:**
- `objective` — WHY this task exists (the user's original intent)
- `verify_source` — Test file to read before implementing
- `lineage` — Deliveries from parent tasks (supports multiple parents for DAG convergence)

**Atomic writes**: All workspace operations use temp-file + rename pattern for crash safety.

The workspace is the builder's single source of truth. Framework idioms are non-negotiable. If something goes wrong that isn't in prior knowledge, the builder blocks — discovery is needed, not more debugging.

## Memory

A unified system capturing what went wrong and what worked:

| File | Purpose |
|------|---------|
| `.ftl/memory.json` | Failures and patterns with semantic retrieval |
| `.ftl/exploration.json` | Aggregated explorer outputs |
| `.ftl/campaign.json` | Active campaign state with DAG |
| `.ftl/archive/` | Completed campaigns |

**Capacity**: 500 failures + 200 patterns (~130KB estimated storage)

**Failures** — Observable errors with executable fixes. Each failure includes: a trigger (the error message), a fix (the action that resolves it), a regex match pattern (to catch in logs), and a cost estimate. Injected into builder's `prior_knowledge` to prevent repeats.

**Patterns** — Reusable approaches that saved significant tokens. High bar: non-obvious insights a senior dev would appreciate. Scored on: blocked→fixed (+3), idiom applied (+2), multi-file (+1), novel approach (+1). Scores are **heuristic guidance** — extract when the workspace demonstrates a transferable technique, skip high scores that succeeded by luck.

### Hybrid Scoring

Memory uses 384-dimensional embeddings (sentence-transformers) for similarity matching. When retrieving context, memories are scored by a hybrid formula:

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
| Task 001 blocks | Failure in 001_slug_blocked.xml |
| Task 002 starts | Workspace with memory + sibling failures |

```xml
<prior_knowledge>
  <failure name="sibling-001_auth-impl" injected="false">
    <trigger>ImportError: fasthtml.core not found</trigger>
    <fix>See blocked workspace for attempted fixes</fix>
  </failure>
</prior_knowledge>
```

**Why at creation time, not planning?** The planner runs once BEFORE any building. Sibling failures only exist AFTER builders encounter them. Dynamic injection ensures freshness.

### Campaign Fingerprinting

Similar past campaigns are discovered through semantic fingerprinting:

```bash
python3 lib/campaign.py find-similar --threshold 0.5 --max 3
```

Returns campaigns with similar objectives, framework, and delta patterns — providing context on what worked (and what didn't) for comparable requests.

## CLI Tools

The `lib/` directory provides Python utilities for orchestration:

| Library | Purpose | Key Commands |
|---------|---------|--------------|
| `exploration.py` | Aggregate explorer outputs | `aggregate-files`, `read`, `write`, `clear` |
| `campaign.py` | Campaign lifecycle and DAG | `create`, `add-tasks`, `ready-tasks`, `cascade-status`, `propagate-blocks`, `complete`, `find-similar`, `get-replan-input`, `merge-revised-plan` |
| `workspace.py` | Task workspace management | `create`, `complete`, `block`, `parse` |
| `memory.py` | Pattern/failure storage | `context`, `add-failure`, `add-pattern`, `query`, `prune`, `feedback`, `add-relationship`, `related`, `stats`, `add-cross-relationship`, `get-solutions` |
| `observer.py` | Automated extraction | `analyze`, `extract-failure` |
| `embeddings.py` | Semantic similarity | LRU cache (5000 entries) |
| `atomicfile.py` | Concurrent write safety | fcntl locks, temp-rename |
| `phase.py` | State transitions | O(1) dispatch |

**Adaptive Re-Planning:** `get-replan-input` generates context when campaigns get stuck. `merge-revised-plan` integrates revised task dependencies without losing completed work.

**DAG Scheduling:** `ready-tasks` returns all tasks whose dependencies are complete, enabling parallel execution. `cascade-status` detects stuck campaigns. `propagate-blocks` marks unreachable tasks.

**Semantic Memory:** `context --objective "text"` retrieves memories ranked by semantic relevance. `query "topic"` searches with semantic ranking.

**Concurrency:** Campaign and memory updates use file locking (`fcntl.LOCK_EX`) for safe parallel execution. All XML writes are atomic (temp + rename).

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
- File locking for concurrent safety
- Atomic XML writes (crash safety)
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

| Module | Lines | Purpose | Status |
|--------|-------|---------|--------|
| `lib/memory.py` | 1,280 | Semantic memory with Bloom filter, decay, pruning, graph | Production |
| `lib/campaign.py` | 847 | DAG scheduling, cycle detection, cascade handling, fingerprinting | Production |
| `lib/workspace.py` | 680 | Atomic XML lifecycle, lineage, sibling injection | Production |
| `lib/observer.py` | 487 | Parallelized pattern/failure extraction | Production |
| `lib/exploration.py` | 364 | Multi-mode aggregation with similar campaigns | Production |
| `lib/phase.py` | 145 | O(1) state transitions | Production |
| `lib/embeddings.py` | 92 | LRU-cached semantic similarity | Production |
| `lib/atomicfile.py` | 110 | fcntl locking, temp-rename pattern | Production |
| `lib/logging_config.py` | 102 | Rotating logs (1MB, 3 backups) | Production |
| `agents/explorer.md` | ~280 | 4-mode exploration spec | — |
| `agents/planner.md` | ~280 | Task decomposition spec | — |
| `agents/builder.md` | ~215 | Implementation FSM spec | — |
| `agents/observer.md` | ~265 | Learning extraction spec | — |
| `agents/shared/` | ~155 | Consolidated reference docs | — |

## What FTL Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user or team collaboration tool (file-based, single-user)
- A model-agnostic orchestration framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
- A replacement for Mem0/Graphiti (complementary, not competing)
