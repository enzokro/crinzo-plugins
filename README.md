# helix

A self-learning orchestrator for Claude Code. Memory that earns its place through demonstrated usefulness.

## The Core Insight

Most agent memory systems accumulate knowledge indefinitely—storing everything, hoping relevance will emerge. The important signals can easily drown as storage noise grows.

Helix inverts this: **memories must prove their worth**. Every insight tracks an effectiveness score (0-1) that updates via EMA on each use. Insights that consistently help rise in ranking; ineffective ones decay toward neutral and eventually prune. The system learns what actually works, not what seemed important at storage time.

```
Insight injected → Builder executes → Outcome reported → Feedback applied (EMA)
       ↑                                                         ↓
       └─────────── Future recalls rank by proven effectiveness ─┘
```

This closes the learning loop. The agent improves through use, not accumulation.

## Why Now

Opus 4.6 broke the pattern. Previous agent harnesses focused on constraining LLM tendencies—scope creep, over-engineering, context drift. They added guardrails, checkpoints, and hand-holding to compensate for model limitations.

Opus 4.6 doesn't need training wheels. It reasons well, follows instructions, and stays on task. Helix builds on this capability jump: prose-driven orchestration, minimal scaffolding, maximum model autonomy. The orchestrator is a markdown file (SKILL.md), not a state machine.

## How It Works

```
/helix <objective>
       │
       ▼
┌──────────────────────────────────────┐
│  EXPLORE (parallel, sonnet)          │
│  Swarm maps codebase structure       │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  RECALL                              │
│  Orchestrator recalls strategic      │
│  insights → CONSTRAINTS for planner  │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  PLAN (opus)                         │
│  Decomposes into task DAG            │
│  Respects CONSTRAINTS from memory    │
│  Tactical insights via hook          │
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
│  Observe cross-task patterns         │
│  Ask user for domain knowledge       │
│  Store validated insights            │
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

Memory flows at two levels: the **RECALL** phase gives the orchestrator strategic context—decomposition constraints, risk areas, sequencing hints—which it synthesizes into a `CONSTRAINTS` block for the planner. Separately, the **SubagentStart hook** injects tactical insights directly into builder and planner prompts. Strategic and tactical memory are complementary; neither duplicates the other.

The LEARN phase is not automated—the orchestrator presents observations and hypotheses to the user via structured options, incorporating domain knowledge the system cannot infer. Options encode cognitive scaffolding; the user confirms, corrects, or provides their own answer.

## Memory That Learns

Unified insight model with semantic deduplication and causal feedback:

```
store("When X, do Y because Z", tags=["pattern"])
  → Embed via snowflake-arctic-embed-m-v1.5 (256-dim)
  → Check semantic similarity (threshold: 0.85)
  → Merge if duplicate, add if new
  → Initial effectiveness: 0.5 (neutral)
```

**Scoring formula (multiplicative):**
```
score = relevance × (0.5 + 0.5 × effectiveness) × recency

eff=1.0 (proven):  score = relevance × 1.0 × recency
eff=0.5 (neutral): score = relevance × 0.75 × recency
eff=0.0 (bad):     score = relevance × 0.5 × recency

recency = max(0.9, 1.0 - 0.001 × days_unused)
```

**Causal feedback (EMA):**
```
new_effectiveness = old × 0.8 + outcome_value × 0.2
outcome_value = 1.0 (delivered) | 0.0 (blocked)
```

Insights start neutral (0.5). ~3 positive outcomes move 0.5 → 0.6. Causal filtering ensures only insights semantically relevant to the task context (cosine ≥ 0.50) receive full EMA updates. Non-causal insights erode 10% toward neutral (above 0.5 only—bad insights don't self-rehabilitate without causal evidence).

**Read-time causal adjustment:** After 3+ uses, effectiveness is scaled by `max(0.3, causal_hits / use_count)`. An insight with raw effectiveness 0.50 but zero causal hits adjusts to 0.15—eventually pruned.

**Derived insights:** BLOCKED outcomes generate prescriptive insights ("When X, be aware that Y can block progress") at `initial_effectiveness=0.35`, below neutral. They must prove themselves to rise.

**8 primitives:** `store`, `recall`, `get`, `feedback`, `decay`, `prune`, `count`, `health`.

## Hook Architecture

Helix uses Claude Code hooks for invisible learning operations:

| Hook | Trigger | Action |
|------|---------|--------|
| SessionStart | Session begins | Initialize venv, persist environment, background embedding warmup |
| SubagentStart | Builder/planner spawns | Recall insights, write sideband file, return `additionalContext` |
| SubagentStop | Any helix agent completes | Extract insights, apply causal feedback, write task status |
| SessionEnd | Session ends | Cleanup ephemeral state, decay dormant insights, prune low performers |

**SubagentStart** is the injection hook. It parses the parent transcript for the task objective, recalls relevant insights (suppressing names already injected into sibling agents for diversity), writes a sideband file with the query embedding for downstream causal attribution, and returns formatted insights as `additionalContext`. If the orchestrator already injected insights in the prompt, the hook skips to avoid duplication.

**SubagentStop** is the extraction hook. Three-phase pipeline with independent error boundaries: (1) write handoff files (task status, explorer results), (2) determine outcome with retry for race conditions, (3) store insights + apply causal feedback + log diagnostics. Each phase failing does not block the others.

**Sideband files** (`.helix/injected/{agent_id}.json`) carry the recall query embedding from inject to extract, enabling causal attribution without re-embedding. Read-and-deleted by SubagentStop; stale files cleaned by SessionEnd.

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
| **Feedback closes the loop** | Outcome updates effectiveness via EMA with causal filtering |
| **Blocking is success** | Unknown errors create learning data, not token burn |
| **Bounded scope** | Relevant files are explicit and auditable |
| **Present over future** | Implement current requests, not anticipated needs |
| **Edit over create** | Modify existing code before creating new files |

## Local-First

Everything stays on your machine:
- SQLite database at `.helix/helix.db` (WAL mode)
- Sideband files at `.helix/injected/` (consume-once)
- Explorer results at `.helix/explorer-results/`
- Task status at `.helix/task-status.jsonl`
- No external API keys for memory services
- No data leaving your system
- No usage fees

## Technical Reference

For implementation details—agent contracts, database schema, CLI reference, scoring formulas, tuning constants—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
