# helix

A self-learning orchestrator for Claude Code. Memory that earns its place through demonstrated usefulness.

## The Core Insight

Most agent memory systems accumulate knowledge indefinitely—storing everything, hoping relevance will emerge. This creates noise that drowns signal.

Helix inverts this: **memories must prove their worth**. Every memory tracks `helped` and `failed` counts. Verification outcomes update these scores automatically. Memories that consistently help rise in ranking; ineffective ones decay and eventually prune. The system learns what actually works, not what seemed important at storage time.

```
Memory injected (auto) → Builder executes → Outcome reported → Feedback applied (auto)
       ↑                                                              ↓
       └──────────────── Future recalls rank by proven effectiveness ─┘
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
│  Memory auto-injected via hook       │
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
│  Execute tasks with memory context   │
│  Auto-feedback on task outcome       │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  OBSERVE + LEARN                     │
│  Learning queue for review           │
│  Update effectiveness scores         │
│  Connect knowledge via graph edges   │
└──────────────────────────────────────┘
```

Three specialized agents, each receiving context tuned to their role. Explorers get known facts to skip redundant discovery. Planners get past decisions and conventions for consistency. Builders get failures to avoid, patterns to apply, and confidence scores to weight advice.

## Memory That Learns

Seven memory types, each with purpose-specific scoring:

| Type | Purpose | Example |
|------|---------|---------|
| **failure** | What went wrong | "Circular import when adding auth middleware" |
| **pattern** | What worked | "Use dependency injection for database connections" |
| **systemic** | Recurring issues | "This codebase has import cycle problems" |
| **fact** | Codebase structure | "Authentication lives in src/auth/" |
| **convention** | Project patterns | "All API routes use async handlers" |
| **decision** | Architectural choices | "Chose PostgreSQL over MongoDB" |
| **evolution** | Recent changes | "Added user profile endpoints yesterday" |

Each type has different decay rates and scoring weights. Facts persist longer (30-day half-life) because codebase structure is stable. Evolution decays fast (7-day half-life) because recent changes matter most when recent.

### Graph Relationships

Memories connect: patterns **solve** failures, issues **co-occur**, failures **cause** other failures. Graph expansion surfaces solutions when you encounter related problems.

```
failure: "Import cycle in auth module"
    ↑
    solves
    ↓
pattern: "Use lazy imports for circular dependencies"
```

When you query about authentication and hit the failure, graph expansion brings the solution along.

## Hook Architecture

Helix uses Claude Code hooks for invisible memory operations:

| Hook | Trigger | Action |
|------|---------|--------|
| PreToolUse(Task) | Agent spawn | Inject relevant memories into prompt |
| SubagentStop | Agent completion | Extract learning candidates to queue |
| PostToolUse(TaskUpdate) | Task outcome | Auto-credit/debit memories |

Memory injection, learning extraction, and feedback attribution happen automatically. The orchestrator focuses on judgment; hooks handle mechanics.

### Confidence Indicators

Builders see effectiveness scores on injected memories:

```
FAILURES_TO_AVOID:
  [75%] Circular import when adding middleware -> Use lazy imports
  [unproven] Database timeout on large queries -> Add connection pooling
```

`[75%]` means this memory helped 75% of the time. Builders weight advice accordingly.

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
| **Feedback closes the loop** | Verification outcomes update memory effectiveness |
| **Blocking is success** | Unknown errors create learning data, not token burn |
| **Bounded scope** | Relevant files are explicit and auditable |
| **Present over future** | Implement current requests, not anticipated needs |
| **Edit over create** | Modify existing code before creating new files |

## Local-First

Everything stays on your machine:
- SQLite database at `.helix/helix.db`
- Injection state at `.helix/injection-state/`
- Learning queue at `.helix/learning-queue/`
- No external API keys for memory services
- No data leaving your system
- No usage fees

## Technical Reference

For implementation details—agent contracts, database schema, CLI reference, scoring formulas—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
