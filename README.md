# Helix (v1.0.0)

A Claude Code orchestrator with integrated memory that learns from every session.

## Introduction

Before Opus 4.5, agentic harnesses focused on working around the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

Helix builds on this shift. While previous harnesses were mostly meant to keep the models from drifting, helix persists knowledge across sessions to build on what we've already done instead of always starting from an empty context window.

## Philosophy

| Principle | Meaning |
|-----------|---------|
| Feedback closes the loop | Every task completion updates memory effectiveness |
| Verify first | Shape work by starting with proof-of-success |
| Bounded scope | Delta files are explicit so humans can audit agent boundaries |
| Present over future | Implement current requests, not anticipated needs |
| Edit over create | Modify what exists before creating something new |
| Blocking is success | Informed handoff creates learning data, prevents budget waste |

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

**Learning compounds, not just stores.** Memory layers store and retrieve; helix closes the loop. Every memory gets a helped/failed ratio updated by actual builder outcomes. Memories that work rise in ranking; memories that don't sink. The system gets smarter through use, not just accumulation.

**Bounded execution, not infinite loops.** Four agents with explicit tool budgets (builders get 5-9 invocations). When a builder exhausts its budget or hits an unknown error, it blocks—creating learning data rather than burning tokens. Delta files are auditable contracts. You always know what the agent is allowed to touch.

**Framework enforcement, not suggestions.** When framework confidence ≥0.6, idiom compliance isn't a warning—it's a hard gate. The builder blocks even if tests pass when framework idioms are violated. This prevents the subtle rot of "working but wrong" code that accumulates across sessions.

**Local-first, no cloud dependency.** SQLite database in `.helix/helix.db`. Your failures, patterns, and workspace history stay on your machine. No API keys for memory services, no usage fees, no data leaving your system.

**Unified architecture, no integration friction.** Memory and orchestration are one system. Direct Python imports, not subprocess calls. The feedback loop closes within a single function call. No external plugin discovery, no silent degradation.

## Development Loop

```
/helix <task>
    │
    ▼
┌─────────────────────────────────────┐
│  EXPLORER (haiku, 6 tools)          │
│  structure │ patterns │ memory │ targets
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  PLANNER (opus)                     │
│  Decompose → Dependencies → Budget  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  BUILDER (opus, budget 5-9)         │
│  Read → Implement → Verify → Report │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│  OBSERVER (opus)                    │
│  Extract failures │ Chunk patterns  │
└─────────────────────────────────────┘
```

**Explorer** (Haiku) gathers codebase context—structure, framework patterns, relevant memories, and candidate files for modification.

**Planner** (Opus) decomposes work into a task DAG with dependencies, budgets, and verification criteria. Registers tasks in Claude Code's native Task system (visible via Ctrl+T).

**Builders** (Opus, budget 5-9) execute tasks within constraints. They block on unknown errors rather than debugging indefinitely. Report DELIVERED or BLOCKED with honest UTILIZED list.

**Observer** (Opus) extracts patterns from outcomes via SOAR chunking. Failures from blocked workspaces become future warnings. Calls `feedback(utilized, injected)` to close the loop.

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <task>` | Full pipeline: explore → plan → build → observe |
| `/helix-query "topic"` | Surface relevant precedent from memory |
| `/helix-stats` | Memory health metrics |

## Memory System

Failures and patterns are stored with 384-dimensional embeddings for semantic retrieval.

**Scoring formula** balances relevance, effectiveness, and recency:

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)
```

Where:
- `effectiveness = helped / (helped + failed)` — default 0.5 if no feedback
- `recency = 2^(-days_since_use / 7)` — ACT-R decay, 7-day half-life

**Feedback loop**: Builders report which memories they actually used. Observer updates helped/failed counts. Memories that consistently help rise in ranking; ineffective ones decay faster.

**Graph relationships** link related failures and patterns (causes, solves, co_occurs). Query with `connected()` to traverse connections.

See [HELIX_OVERVIEW.md](../docs/HELIX_OVERVIEW.md) for embedding details, deduplication rules, and maintenance operations.

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

## Examples

### Single Task

```bash
/helix add CRUD endpoints for user profiles with validation
```

Explorer maps structure and detects framework. Planner produces spec→impl DAG. Builders execute with memory injection. Observer extracts patterns from any blocked→fixed recovery.

### Learning Across Sessions

```bash
# Session 1: Builder blocks on circular import error
# Observer extracts failure with fix

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

## Documentation

For comprehensive technical reference—agent specifications, database schemas, configuration constants, and CLI tools—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
