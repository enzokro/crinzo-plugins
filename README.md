# helix

A self-learning orchestrator for Claude Code. Memory that earns its place through demonstrated usefulness.

## The Core Insight

Most agent memory systems accumulate knowledge indefinitely—storing everything, hoping relevance will emerge. This creates noise that drowns signal.

Helix inverts this: **memories must prove their worth**. Every insight tracks an effectiveness score (0-1) that updates via EMA on each use. Insights that consistently help rise in ranking; ineffective ones decay toward neutral and eventually prune. The system learns what actually works, not what seemed important at storage time.

```
Insight injected → Builder executes → Outcome reported → Feedback applied (EMA)
       ↑                                                         ↓
       └─────────── Future recalls rank by proven effectiveness ─┘
```

This closes the learning loop. The agent improves through use, not accumulation.

## Why Now

Opus 4.5 broke the pattern. Previous agent harnesses focused on constraining LLM tendencies—scope creep, over-engineering, context drift. They added guardrails, checkpoints, and hand-holding to compensate for model limitations.

Opus 4.5 doesn't need training wheels. It reasons well, follows instructions, and stays on task. Helix builds on this capability jump: prose-driven orchestration, minimal scaffolding, maximum model autonomy. The orchestrator is a markdown file (SKILL.md), not a state machine.

## How It Works

```
/helix <objective>
       │
       ▼
┌──────────────────────────────────────┐
│  EXPLORE (parallel, haiku)           │
│  Swarm maps codebase structure       │
│  Insights auto-injected via hook     │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  PLAN (opus)                         │
│  Decomposes into task DAG            │
│  Context auto-injected via hook      │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  BUILD (parallel, opus)              │
│  Execute tasks with insight context  │
│  Auto-feedback on task outcome       │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  LEARN                               │
│  SubagentStop extracts insights      │
│  Applies EMA feedback to injected    │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  COMPLETE                            │
│  Verify learning loop closed         │
│  Report session summary              │
└──────────────────────────────────────┘
```

Three specialized agents, each receiving context tuned to their role. Explorers discover codebase structure. Planners decompose objectives into tasks. Builders execute tasks and report outcomes. Learning extraction and feedback attribution happen automatically via hooks.

## Memory That Learns

Unified insight model with semantic deduplication:

```
store("When X, do Y because Z", tags=["pattern"])
  → Check semantic similarity (threshold: 0.85)
  → Merge if duplicate, add if new
  → Initial effectiveness: 0.5 (neutral)
```

**Scoring formula:**
```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)
recency = 2^(-days_since_use / 14)
```

**EMA feedback:**
```
new_effectiveness = old × 0.9 + outcome_value × 0.1
outcome_value = 1.0 (delivered) | 0.0 (blocked)
```

Insights start neutral (0.5), move toward 1.0 with success, toward 0.0 with failure. After enough uses, low performers get pruned.

## Hook Architecture

Helix uses Claude Code hooks for invisible learning operations:

| Hook | Trigger | Action |
|------|---------|--------|
| SessionStart (×2) | Session begins | Initialize venv/database, set up environment |
| SubagentStop | Agent completion | Extract insights, apply EMA feedback |
| SessionEnd | Session ends | Log session summary, cleanup old queue files |

Memory injection happens in the orchestrator (SKILL.md) and via inject_memory.py hook. Learning extraction and feedback attribution happen automatically in extract_learning.py. The orchestrator focuses on judgment; hooks handle mechanics.

### Confidence Indicators

Builders see effectiveness scores on injected insights:

```
INSIGHTS (from past experience):
  - [75%] When adding middleware, check for circular imports first
  - [50%] Database connections should use pooling for high-traffic endpoints
```

`[75%]` means this insight has demonstrated 75% effectiveness. `[50%]` is neutral—no feedback yet. Builders weight advice accordingly.

## Installation

```bash
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins
claude plugin install helix@crinzo-plugins
```

## Usage

```bash
/helix add user authentication with JWT tokens
/helix refactor the payment processing module
/helix fix the flaky integration tests
```

Query memory directly:
```bash
/helix-query "authentication patterns"
/helix-stats  # Memory health metrics
```

## When to Use

**Use helix for:**
- Multi-step work that benefits from exploration first
- Projects where past failures should inform future work
- Complex objectives needing task coordination
- Work that creates reusable precedent

**Skip helix for:**
- Quick single-file changes
- Exploratory prototyping where wandering is fine
- One-off tasks with no future value

## Design Principles

| Principle | Meaning |
|-----------|---------|
| **Feedback closes the loop** | Outcome updates effectiveness via EMA |
| **Blocking is success** | Unknown errors create learning data, not token burn |
| **Bounded scope** | Relevant files are explicit and auditable |
| **Present over future** | Implement current requests, not anticipated needs |
| **Edit over create** | Modify existing code before creating new files |

## Local-First

Everything stays on your machine:
- SQLite database at `.helix/helix.db`
- Injection state at `.helix/injection-state/`
- Explorer results at `.helix/explorer-results/`
- Task status at `.helix/task-status.jsonl`
- No external API keys for memory services
- No data leaving your system
- No usage fees

## Technical Reference

For implementation details—agent contracts, database schema, CLI reference, scoring formulas—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
