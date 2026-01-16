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

## Commands

| Command | Purpose |
|---------|---------|
| `/ftl <task>` | Full pipeline: explore → plan → build → observe |
| `/ftl campaign "objective"` | Multi-task campaign with DAG parallelization |
| `/ftl query "topic"` | Surface relevant precedent from memory (semantic ranking) |
| `/ftl status` | Current campaign and workspace state |

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

The workspace is the builder's single source of truth. Framework idioms are non-negotiable. If something goes wrong that isn't in prior knowledge, the builder blocks — discovery is needed, not more debugging.

## Memory

A unified system capturing what went wrong and what worked:

| File | Purpose |
|------|---------|
| `.ftl/memory.json` | Failures and patterns with semantic retrieval |
| `.ftl/exploration.json` | Aggregated explorer outputs |
| `.ftl/campaign.json` | Active campaign state with DAG |
| `.ftl/archive/` | Completed campaigns |

**Failures** — Observable errors with executable fixes. Each failure includes: a trigger (the error message), a fix (the action that resolves it), a regex match pattern (to catch in logs), and a cost estimate. Injected into builder's `prior_knowledge` to prevent repeats.

**Patterns** — Reusable approaches that saved significant tokens. High bar: non-obvious insights a senior dev would appreciate. Scored on: blocked→fixed (+3), idiom applied (+2), multi-file (+1), novel approach (+1). Score ≥3 gets extracted.

**Semantic retrieval** — Memory uses 384-dimensional embeddings (sentence-transformers) for similarity matching. When retrieving context, memories are scored by hybrid relevance:

```
score = relevance × log₂(cost + 1)
```

This balances "how relevant is this to my current task?" with "how expensive was this to discover?" — ensuring you don't repeat expensive mistakes while avoiding irrelevant-but-costly noise.

**Deduplication** — 85% semantic similarity threshold prevents near-duplicate entries. Sources are merged when duplicates detected.

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
importance = log₂(value + 1) × age_decay × access_boost × effectiveness
```

- **value**: cost (failures) or saved tokens (patterns)
- **age_decay**: exponential decay with 30-day half-life
- **access_boost**: 1 + 0.1 × access_count
- **effectiveness**: 0.5 (unhelpful) to 1.5 (very helpful) based on feedback

### Graph Relationships

Failures and patterns can be linked:

```bash
python3 lib/memory.py add-relationship auth-timeout database-connection --type failure

# Later retrieval with multi-hop traversal
python3 lib/memory.py related auth-timeout --max-hops 2
# Returns: database-connection (1 hop), connection-retry (2 hops)
```

This enables discovery across related issues: "I'm seeing auth timeouts — what caused those, and what fixed the cause?"

### Pruning

Memory self-manages through importance-based pruning:

```bash
python3 lib/memory.py prune --max-failures 500 --max-patterns 200 --min-importance 0.1
```

Low-importance entries (old, unused, ineffective) are pruned first. The system maintains bounded size while preserving high-value knowledge.

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

**Cycle detection**: Dependencies are validated at registration. Cyclic graphs are rejected with a clear error showing the cycle path.

**Cascade handling**: When a parent task blocks, child tasks become unreachable. The orchestrator detects stuck campaigns and propagates blocks to unreachable tasks with `blocked_by` references. Campaigns complete gracefully with partial success rather than hanging indefinitely.

### Sibling Failure Injection

When a task blocks, its failure is injected into subsequent tasks *before* the Observer runs:

```xml
<prior_knowledge>
  <sibling_failure seq="002" slug="auth-impl">
    <trigger>ImportError: fasthtml.core not found</trigger>
    <reason>Wrong import path for FastHTML 0.7+</reason>
  </sibling_failure>
</prior_knowledge>
```

This enables intra-campaign learning — later tasks benefit from earlier failures immediately, without waiting for the Observer to extract patterns.

### Campaign Fingerprinting

Similar past campaigns are discovered through semantic fingerprinting:

```bash
python3 lib/exploration.py similar-campaigns "implement OAuth flow"
```

Returns campaigns with similar objectives, providing context on what worked (and what didn't) for comparable requests.

## CLI Tools

The `lib/` directory provides Python utilities for orchestration:

| Library | Purpose | Key Commands |
|---------|---------|--------------|
| `exploration.py` | Aggregate explorer outputs | `aggregate-files`, `read`, `write`, `clear`, `similar-campaigns` |
| `campaign.py` | Campaign lifecycle and DAG | `create`, `add-tasks`, `ready-tasks`, `cascade-status`, `propagate-blocks`, `complete` |
| `workspace.py` | Task workspace management | `create`, `complete`, `block`, `parse` |
| `memory.py` | Pattern/failure storage | `context`, `add-failure`, `add-pattern`, `query`, `prune`, `feedback`, `add-relationship`, `related`, `stats` |
| `embeddings.py` | Semantic similarity | Used internally by memory.py |
| `atomicfile.py` | Concurrent write safety | Used internally by campaign.py, memory.py |

**DAG Scheduling:** `ready-tasks` returns all tasks whose dependencies are complete, enabling parallel execution. `cascade-status` detects stuck campaigns. `propagate-blocks` marks unreachable tasks.

**Semantic Memory:** `context --objective "text"` retrieves memories ranked by semantic relevance. `query "topic"` searches with semantic ranking.

**Concurrency:** Campaign and memory updates use file locking (`fcntl.LOCK_EX`) for safe parallel execution.

## Examples

```bash
# Execute a task — full pipeline runs
/ftl add user authentication

# Multi-task campaign
/ftl campaign "implement OAuth with Google and GitHub"

# Query past patterns (semantic search)
/ftl query session handling

# Check status
/ftl status
```

## What's Automated vs. What's Documented

FTL operates on two layers:

| Layer | How It Works | Reliability |
|-------|--------------|-------------|
| **Python Infrastructure** | Deterministic code | Guaranteed |
| **Agent Instructions** | Claude following markdown specs | Probabilistic |

**Automated (100% reliable):**
- Semantic memory retrieval and hybrid scoring
- DAG scheduling and cycle detection
- Cascade handling for blocked parents
- Sibling failure injection
- Block verification in Observer
- Pattern/failure deduplication (85% threshold)
- Memory feedback recording
- File locking for concurrent safety
- Pruning based on importance scores

**Documented (agent judgment):**
- Cross-workspace synthesis and relationship discovery
- Idiom compliance checking (Builder follows spec)
- Pattern scoring (≥3 points threshold)
- Override of false positives in Observer

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
| `lib/memory.py` | 776 | Semantic memory with decay, pruning, graph | Production |
| `lib/campaign.py` | 788 | DAG scheduling, cycle detection, cascade handling | Production |
| `lib/workspace.py` | 583 | XML workspace lifecycle, lineage, sibling injection | Production |
| `lib/exploration.py` | 364 | Multi-mode aggregation with similar campaigns | Production |
| `lib/observer.py` | 410 | Automated pattern/failure extraction | Production |
| `lib/embeddings.py` | 51 | Semantic similarity with graceful fallback | Production |
| `lib/atomicfile.py` | 38 | fcntl locking for concurrent JSON | Production |
| `agents/explorer.md` | ~250 | 4-mode exploration spec | — |
| `agents/planner.md` | ~350 | Task decomposition spec | — |
| `agents/builder.md` | ~280 | Implementation spec | — |
| `agents/observer.md` | ~265 | Learning extraction spec | — |

**Total**: ~3,000 lines production Python, ~1,100 lines agent specs, 7 test modules.

## What FTL Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user or team collaboration tool (file-based, single-user)
- A model-agnostic orchestration framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
