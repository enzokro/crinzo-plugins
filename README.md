# ftl (v2.4.18)

A Claude Code orchestrator that builds knowledge over time.

## Introduction

Before Opus 4.5, agentic harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`ftl` builds on this shift. While previous harnesses were mostly meant to keep the models from drifting, `ftl` persists knowledge across sessions to build on what we've already done instead of always starting from an empty context window.

## Philosophy

| Principle               | Meaning                                                           |
| ----------------------- | ----------------------------------------------------------------- |
| **Memory compounds**    | Each task leaves the system smarter                               |
| **Verify first**        | Shape work by starting with proof-of-success                      |
| **Bounded scope**       | Workspace files are explicit so humans can audit agent boundaries |
| **Present over future** | Implement current requests, not anticipated needs                 |
| **Edit over create**    | Modify what exists before creating something new                  |
| **Blocking is success** | Informed handoff creates learning data, prevents budget waste     |

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

## Why ftl?

**Learning compounds, not just stores.** Memory layers store and retrieve; ftl closes the loop. Every failure gets a `helped/failed` ratio updated by actual builder outcomes. Memories that work persist; memories that don't decay. The system gets smarter through use, not just accumulation.

**Bounded execution, not infinite loops.** Four agents with explicit tool budgets (builders get 5-9 invocations). When a builder exhausts its budget or hits an unknown error, it blocks—creating learning data rather than burning tokens. Workspace files are auditable contracts. You always know what the agent is allowed to touch.

**Framework enforcement, not suggestions.** When framework confidence ≥0.6, idiom compliance isn't a warning—it's a hard gate. The builder blocks even if tests pass when framework idioms are violated. This prevents the subtle rot of "working but wrong" code that accumulates across sessions.

**Local-first, no cloud dependency.** SQLite database in `.ftl/ftl.db`. Your failures, patterns, and campaign history stay on your machine. No API keys for memory services, no usage fees, no data leaving your system.

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
    ▼
┌─────────────────────────────────────┐
│  PLANNER                            │
│  Decompose → Verify → Budget → Order│
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  BUILDER (parallel where possible)  │
│  Read spec → Implement → Verify     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  OBSERVER                           │
│  Verify blocks → Extract patterns   │
└─────────────────────────────────────┘
```

**Explorers** (Haiku) gather codebase context in parallel—structure, framework patterns, relevant memories, and candidate files for modification.

**Planner** (Opus) decomposes work into a task DAG with dependencies, budgets, and verification criteria.

**Builders** (Opus, budget 5-9) execute tasks in parallel where dependencies allow. They block on unknown errors rather than debugging indefinitely.

**Observer** (Opus) extracts patterns from outcomes. Blocks are verified; false positives are skipped. Patterns require a minimum score to be stored.

## Commands

| Command | Purpose |
|---------|---------|
| `/ftl <task>` | Full pipeline: explore → plan → build → observe |
| `/ftl campaign "objective"` | Multi-task campaign with DAG parallelization |
| `/ftl query "topic"` | Surface relevant precedent from memory |
| `/ftl status` | Current campaign and workspace state |
| `/ftl stats` | Memory health metrics |
| `/ftl prune` | Remove low-importance entries |
| `/ftl related "name"` | Graph traversal from an entry |
| `/ftl similar` | Find similar past campaigns |

## Memory System

Failures and patterns are stored with 384-dimensional embeddings for semantic retrieval.

**Hybrid scoring** balances relevance, cost, age, and track record:
```
score = relevance × log₂(cost + 1) × help_ratio × age_decay
```

**Feedback loop**: Builders report which memories they actually used. Observer updates `helped/failed` ratios. Memories that consistently help persist; ineffective ones decay faster.

**Graph relationships** link related failures and patterns (causes, solves, co-occurs). Query with `/ftl related` to traverse connections.

See [FTL_OVERVIEW.md](docs/FTL_OVERVIEW.md) for embedding details, tiered injection thresholds, deduplication rules, and pruning algorithms.

## Campaign DAG

Campaigns support multi-parent task dependencies with parallel execution:

```
001 (spec-auth) ──→ 003 (impl-auth) ──┐
                                      ├──→ 005 (integrate)
002 (spec-api) ──→ 004 (impl-api) ───┘
```

When a parent blocks, **adaptive re-planning** triggers: the planner receives blocked context plus completed work and generates alternative paths. Campaigns complete gracefully with partial success rather than hanging.

**Sibling failure injection**: When task 001 blocks, its failure is injected into task 002's workspace at creation time—parallel branches learn from each other within a single campaign.

See [FTL_OVERVIEW.md](docs/FTL_OVERVIEW.md) for cycle detection, cascade handling, and re-planning algorithms.

## Examples

### Single Task
```bash
/ftl add CRUD endpoints for user profiles with validation
```
Explorers map structure and detect framework. Planner produces spec→impl DAG. Builders execute. Observer extracts patterns from any blocked→fixed recovery.

### Multi-Task Campaign
```bash
/ftl campaign "add real-time notifications with WebSocket support"
```
Independent branches execute in parallel. Convergent tasks wait for all parents. Blocks trigger re-planning with alternative paths.

### Learning Across Sessions
```bash
# Session 1: Builder blocks on FT concatenation error
# Observer extracts failure with fix

# Session 2 (weeks later): Different project
/ftl add a comment section component
# Explorer retrieves the failure; builder avoids the mistake
```

## When to Use

**Use ftl when:**
- Work should persist as precedent
- You want bounded, reviewable scope
- Complex objectives need multi-task coordination
- Framework-specific development with idiom enforcement
- Past failures should inform future work

**Skip ftl when:**
- Exploratory prototyping (let models wander)
- Quick one-offs with no future value
- Team collaboration (single-user design)
- Novel frameworks without idiom definitions

## Documentation

For comprehensive technical reference—agent specifications, state machines, database schemas, configuration constants, and CLI tools—see **[docs/FTL_OVERVIEW.md](docs/FTL_OVERVIEW.md)**.
