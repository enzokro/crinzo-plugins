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
│  RECALL                              │
│  Query memory for strategic insights │
│  → CONSTRAINTS + exploration targets │
└──────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────┐
│  EXPLORE (parallel, sonnet)          │
│  Swarm maps codebase structure       │
│  Scope informed by recalled insights │
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

Three specialized agents, each receiving context tuned to their role:

- **Explorers** map codebase structure via a 5-step procedure (orient → map interfaces → trace dependencies → sample implementations → locate tests), receiving recalled insight context to prioritize areas the system has learned matter.
- **Planners** decompose objectives into task DAGs with explicit task-sizing rules, dependency validation (data dependencies only—conceptual relatedness is not a dependency), concrete verification commands per task type, and anti-pattern guardrails.
- **Builders** execute tasks through structured phases (pre-flight → implement → verify → failure diagnosis) with categorized error handling and two-attempt retry logic.

Learning extraction and feedback attribution happen automatically via hooks.

Memory flows at two levels: the **RECALL** phase gives the orchestrator strategic context—decomposition constraints, risk areas, sequencing hints—which it synthesizes into a `CONSTRAINTS` block for the planner and exploration targets for the explorer swarm. Separately, the **SubagentStart hook** injects tactical insights directly into builder and planner prompts. Strategic and tactical memory are complementary; neither duplicates the other.

The LEARN phase is not automated—the orchestrator presents observations and hypotheses to the user via structured options, incorporating domain knowledge the system cannot infer. Options encode hypotheses derived from block reasons and task context; the user confirms, corrects, or provides their own answer.

## Memory That Learns

Unified insight model with semantic deduplication and causal feedback:

```
store("When X, do Y because Z", tags=["pattern"])
  → Embed via snowflake-arctic-embed-m-v1.5 (768-dim)
  → Check semantic similarity (threshold: 0.85)
  → Merge if duplicate, add if new
  → Initial effectiveness: 0.5 (neutral)
```

**Hybrid retrieval with RRF fusion:**
```
recall(query)
  → Vector: embed(query) → dot product against all insights → rank by cosine sim
  → Keyword: FTS5 MATCH on insight content + tags → rank by BM25
  → Fuse: RRF score = 1/(K + vec_rank) + 1/(K + fts_rank)   [K=60]
  → Final: rrf_score × (0.5 + 0.5 × effectiveness) × recency

eff=1.0 (proven):  score = rrf × 1.0 × recency
eff=0.5 (neutral): score = rrf × 0.75 × recency
eff=0.0 (bad):     score = rrf × 0.5 × recency

recency = max(0.9, 1.0 - 0.001 × days_unused)
```

FTS5 boosts ranking for exact keyword matches (e.g., `ECONNREFUSED`, `JWT`, `SQLAlchemy`) that vector similarity may underweight. Degrades gracefully to pure vector when FTS5 is unavailable. The `min_relevance` gate applies to all candidates—FTS cannot bypass it.

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

**SubagentStart** is the injection hook. It parses the parent transcript for the task objective, recalls up to 3 relevant insights (suppressing names already injected into sibling agents for diversity), writes a sideband file with the query embedding for downstream causal attribution, and returns formatted insights as `additionalContext`. If the orchestrator already injected insights in the prompt, the hook skips to avoid duplication.

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

Plan-mode alternative—produces an insight-informed implementation plan for approval without executing:
```bash
/helix-meta-planner redesign the caching layer
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

## How Helix Compares

Agent memory systems fall into four categories: static instruction files (CLAUDE.md, Cursor rules), auto-generated notes (Claude auto-memory, GitHub Copilot memory), MCP-based memory servers (Mem0, Zep/Graphiti), and Claude Code plugins with memory (claude-mem, engram, episodic-memory). Helix occupies a distinct position: it is the only production system that closes the loop from task outcome back to memory quality through causal feedback.

| System | Retrieval | Auto-Capture | Feedback Loop | Causal Attribution | Orchestration |
|--------|-----------|:---:|:---:|:---:|:---:|
| CLAUDE.md / Cursor rules | Full injection (no search) | No | No | No | No |
| Claude auto-memory | Full injection (200 lines) | Semi | No | No | No |
| GitHub Copilot memory | Citation validation | Yes | TTL (28-day expiry) | No | No |
| [Mem0](https://github.com/mem0ai/mem0) | Semantic (vector DB) | Optional | LLM-as-judge at write time | No | No |
| [Zep/Graphiti](https://github.com/getzep/graphiti) | Hybrid (cosine + BM25 + graph) | Yes | Temporal invalidation | No | No |
| [claude-mem](https://github.com/thedotmack/claude-mem) | 3-layer progressive | Yes | Implicit (usage patterns) | No | No |
| [engram](https://github.com/foramoment/engram-ai-memory) | Cosine + graph-hop | Yes | Ebbinghaus decay | No | No |
| **Helix** | Hybrid (vector + FTS5, RRF fusion) | Yes | EMA + causal filtering + asymmetric erosion/decay + prune | Yes | Yes |

**Closed feedback loop.** Most memory systems are write-only (CLAUDE.md, auto-memory) or perform write-time curation where an LLM decides what to keep (Mem0). Neither approach adjusts memory quality based on whether the memory actually helped. Research on accumulation-based systems confirms sustained performance decline from memory inflation ([Memory-R1](https://arxiv.org/abs/2508.19828), [MEM1](https://arxiv.org/abs/2506.15841)). Helix updates each insight's effectiveness via EMA after every task outcome, with asymmetric erosion ensuring bad insights do not self-rehabilitate without positive causal evidence.

**Causal attribution.** Among production systems, none distinguish "this memory was present in the agent's context" from "this memory was relevant to what the agent did." Among research systems, only [Reflexion](https://arxiv.org/abs/2303.11366) (verbal self-reflection), [ExpeL](https://arxiv.org/abs/2308.10144) (trajectory comparison), and Memory-R1 (RL reward signal) approach this. Helix implements explicit per-memory causal similarity: the query embedding from injection is carried through a sideband file and compared against the task context via vectorized dot product (threshold 0.50). Only causally relevant insights receive full EMA feedback; non-causal ones erode toward neutral.

**Orchestration integration.** Memory is not a separate service queried on demand. It is woven into the explore/plan/build lifecycle at two granularities: the RECALL phase provides strategic context (constraints, risk areas, exploration targets) that shapes decomposition, while the SubagentStart hook provides tactical context that shapes execution. Cross-agent diversity is maintained via sideband files, ensuring parallel builders receive different insights.

**Research alignment.** Helix's scoring formula (`relevance x effectiveness x recency`) parallels the composite retrieval score from [Generative Agents](https://arxiv.org/abs/2304.03442). Its extraction pipeline aligns with ExpeL's trajectory-based insight extraction. The emerging RL frontier ([Memory-R1](https://arxiv.org/abs/2508.19828), [MEM1](https://arxiv.org/abs/2506.15841), [mem-agent](https://huggingface.co/blog/driaforall/mem-agent-blog)) trains agents to learn *when* to remember through reinforcement — a natural next step beyond helix's rule-based feedback model.

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
