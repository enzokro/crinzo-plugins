# helix

A self-learning orchestrator for Claude Code. Memory that earns its place through demonstrated usefulness.

## The Core Insight

Most agent memory systems accumulate knowledge indefinitely—storing everything, hoping relevance will emerge. The important signals can easily drown as storage noise grows.

Helix inverts this: **memories must prove their worth**. Every insight tracks an effectiveness score (0-1) that updates via weighted EMA based on causal similarity strength. Insights that consistently help rise in ranking; ineffective ones decay toward neutral and eventually prune. The system learns what actually works, not what seemed important at storage time.

```
Insight injected → Builder executes → Outcome reported → Weighted feedback (similarity-proportional)
       ↑                                                         ↓
       └─────────── Future recalls rank by proven effectiveness ─┘
                          ↕ graph neighbors
                    ↕ velocity boost for active insights
              ↕ cross-session pattern synthesis
```

This closes the learning loop. Insights also form a graph—auto-linked by semantic similarity at storage, connected by provenance (`led_to`) when one insight spawns another. Recall can traverse these edges, surfacing related knowledge that keyword and vector search alone would miss.

## Why Now

Opus 4.6 broke the pattern. Previous agent harnesses focused on constraining LLM tendencies—scope creep, over-engineering, context drift. They added guardrails, checkpoints, and hand-holding to compensate for model limitations.

Opus 4.6 doesn't need training wheels. It reasons well, follows instructions, and stays on task. Helix builds on this capability jump: prose-driven orchestration, minimal scaffolding, maximum model autonomy. The orchestrator is a markdown file (SKILL.md), not a state machine.

## How It Works

```
/helix <objective>
       │
       ▼
┌──────────────────────────────────────┐
│  RECALL (graph_hops=1)               │
│  Query memory for strategic insights │
│  Graph-expand via similar/led_to     │
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
│  Observe patterns + check provenance │
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

Memory flows at two levels: the **RECALL** phase gives the orchestrator strategic context—decomposition constraints, risk areas, sequencing hints—which it synthesizes into a `CONSTRAINTS` block for the planner and exploration targets for the explorer swarm. Separately, the **SubagentStart hook** injects tactical insights directly into builder and planner prompts. Both use `graph_hops=1` (the default), expanding results through `similar` and `led_to` edges to surface related insights beyond direct vector/keyword matches. Strategic and tactical memory are complementary; neither duplicates the other.

The LEARN phase is not automated—the orchestrator presents observations and hypotheses to the user via structured options, incorporating domain knowledge the system cannot infer. For BLOCKED tasks, it checks insight ancestry via `led_to` provenance edges, identifying whether injected insights came from a low-effectiveness lineage that may be propagating errors. Options encode hypotheses derived from block reasons, task context, and insight provenance; the user confirms, corrects, or provides their own answer. User-provided insights skip dedup merge—human corrections always enter the feedback loop independently, where they must prove themselves against the existing version.

## Memory That Learns

Unified insight model with semantic deduplication and causal feedback:

```
store("When X, do Y because Z", tags=["pattern"])
  → Security scan (prompt injection, credential leaks, invisible unicode, exfiltration patterns)
  → Embed via snowflake-arctic-embed-m-v1.5 (768-dim)
  → If tagged "user-provided": skip dedup (human corrections always get their own row)
  → Otherwise: check semantic similarity (threshold: 0.85), merge if duplicate
  → Auto-link to related insights (0.60 ≤ sim < 0.85) as 'similar' edges
  → Initial effectiveness: 0.5 (neutral)
```

**Hybrid retrieval with RRF fusion + graph expansion:**
```
recall(query, graph_hops=1)
  → Vector: embed(query) → dot product against all insights → rank by cosine sim
  → Keyword: FTS5 MATCH on insight content + tags → rank by BM25
  → Fuse: RRF score = 1/(K + vec_rank) + 1/(K + fts_rank)   [K=60]
  → Final: rrf_score × (0.5 + 0.5 × effectiveness) × recency × (1 + velocity_boost)
  → velocity_boost = min(0.10, recent_uses × 0.02)  [14-day window]
  → Graph expansion: top results' neighbors via similar/led_to edges (score × 0.7 discount)
  → Results carry _hop: 0 (direct) or 1 (graph-expanded)

eff=1.0 (proven):  score = rrf × 1.0 × recency
eff=0.5 (neutral): score = rrf × 0.75 × recency
eff=0.0 (bad):     score = rrf × 0.5 × recency

recency = max(0.85, 1.0 - 0.003 × days_unused)
```

FTS5 boosts ranking for exact keyword matches (e.g., `ECONNREFUSED`, `JWT`, `SQLAlchemy`) that vector similarity may underweight. Degrades gracefully to pure vector when FTS5 is unavailable. The `min_relevance` gate applies to all candidates—FTS cannot bypass it. Graph expansion is best-effort; failure falls back to direct results only.

**Causal feedback (weighted EMA):**
```
weight = max(0, (similarity - 0.50) / 0.50)    [0.0 at threshold, 1.0 at perfect match]
new_effectiveness = old × (1 - 0.2 × weight) + outcome_value × 0.2 × weight
outcome_value = 1.0 (delivered) | 0.3 (partial) | 0.0 (blocked)
```

Insights start neutral (0.5). ~3 positive outcomes move 0.5 → 0.6. Causal filtering ensures only insights semantically relevant to the task context (cosine ≥ 0.50) receive EMA updates **proportional to their similarity strength** — a barely-causal insight (sim=0.51) gets near-zero update while a strongly-causal one (sim=0.95) gets nearly full EMA. Non-causal insights erode 9% toward neutral (above 0.5 only—bad insights don't self-rehabilitate without causal evidence).

**Read-time causal adjustment:** After 3+ uses, effectiveness is scaled by `max(0.33, causal_hits / use_count)`. An insight with raw effectiveness 0.50 but zero causal hits adjusts to 0.165—eventually pruned.

**Knowledge generality:** Each causal feedback event carries the task context embedding. Over time, the system tracks the semantic diversity of contexts where an insight proves useful (Welford's algorithm on cosine space). High diversity = principle (general knowledge, decays at half the normal rate). Low diversity = observation (narrow knowledge, decays normally). The system discovers what kind of knowledge each insight represents through measured behavior, not classification.

**Usage velocity:** Recent causal feedback events (14-day window) boost recall scoring by up to 10%. Insights experiencing a usage spike rank higher than dormant ones with identical effectiveness. Velocity resets automatically when feedback events age out.

**Procedural insights:** Insights tagged `procedure` render as numbered steps when injected, enabling multi-step recipes that participate in the normal feedback loop. Unlike static skill systems, procedures that stop working decay and prune automatically.

**Derived insights:** BLOCKED and PARTIAL outcomes generate prescriptive insights ("When X, be aware that Y can block progress") at `initial_effectiveness=0.35`, below neutral. They must prove themselves to rise.

**Graph memory:** Insights form a lightweight knowledge graph via the `insight_edges` table (schema v15). Two relation types:

- **`similar`** — undirected, auto-created by `store()`. Reuses the dedup similarity vector; candidates with `0.60 ≤ sim < 0.85` get linked (top 5 per insert). Zero extra DB queries beyond dedup.
- **`led_to`** — directional, created by `extract_learning` Phase 3d. When a BLOCKED outcome generates a derived insight, `led_to` edges connect the causal parent insights to the new child. Weight 1.0. Tracks provenance: which insights contributed to spawning new knowledge.

Graph expansion (default `graph_hops=1`) fetches neighbors via a single bidirectional JOIN, scores them against the query with a `HOP_DISCOUNT (0.7)` multiplier, and merges into the main result set. The `min_relevance` gate and `suppress_names` still apply. All recall paths—strategic, tactical, and CLI—use graph expansion by default. Pass `graph_hops=0` to disable.

Prune cleans orphaned edges inline (manual CASCADE — FK pragma not enabled). `health()` reports edge statistics: total edges, connected ratio, average edges per insight.

**Session archive:** Every subagent completion is archived in `session_log` (schema v13) with FTS5 indexing. Stores agent type, outcome, summary (including orchestrator CONSTRAINTS/RISK_AREAS when available), and transcript hash. Enables cross-session pattern detection.

**Cross-session synthesis:** At session end, the system clusters archived failure summaries by embedding similarity (agglomerative clustering, threshold 0.60). Recurring failure patterns with sufficient evidence (confidence = tightness x sqrt(count) >= 1.5) become candidate insights, stored at initial_effectiveness=0.45 — above derived (0.35) but below neutral (0.5). Existing insights matching the pattern receive reinforcement feedback instead of duplication. This is the slow feedback loop: session_log -> semantic clustering -> insight candidates -> normal feedback evaluation.

**Content security:** A security scanner gates `store()` before embedding computation. 14 regex patterns across 4 categories: prompt injection (5), credential leaks — generic (1, relaxed for prescriptive insights) and provider-specific (4, never relaxed), invisible unicode (1), exfiltration (3). Prescriptive insight format ("When X, be aware that Y") is recognized and exempted from generic credential checks, preventing false positives on legitimate security-related insights.

**8 core primitives** (`store`, `recall`, `get`, `feedback`, `decay`, `prune`, `count`, `health`) **+ observability** (`stats` CLI subcommand reports effectiveness distribution, context_spread distribution, velocity distribution, top-connected graph nodes, session_log outcome summary). `health()` includes `loop_coverage`—fraction of insights that have cycled through feedback—surfacing whether the system is learning or just accumulating. Graph operations (`add_edges`, `get_neighbors`, `delete_edges_for`) in `lib/memory/edges.py`. Analytics (`graph_analytics`: connected components, articulation points, density, isolates) in `lib/memory/analytics.py`. CLI: `neighbors` subcommand for graph inspection.

## Hook Architecture

Helix uses Claude Code hooks for invisible learning operations:

| Hook | Trigger | Action |
|------|---------|--------|
| SessionStart | Session begins | Initialize venv, persist environment, background embedding warmup |
| SubagentStart | Builder/planner spawns | Recall insights, capture orchestrator CONSTRAINTS/RISK_AREAS, write sideband file, return `additionalContext` |
| SubagentStop | Any helix agent completes | Extract insights, apply causal feedback, create provenance edges, archive to session_log, write task status |
| SessionEnd | Session ends | Cleanup ephemeral state, decay dormant insights, prune low performers, cross-session synthesis |

**SubagentStart** is the injection hook. It parses the parent transcript for the task objective, recalls up to 3 relevant insights (suppressing names already injected into sibling agents for diversity), writes a sideband file with the query embedding for downstream causal attribution, and returns formatted insights as `additionalContext`. If the orchestrator already injected insights in the prompt, the hook skips to avoid duplication. It also captures CONSTRAINTS and RISK_AREAS sections from the orchestrator's prompt via regex extraction, passing them through the sideband file to enrich session_log archival.

**SubagentStop** is the extraction hook. Five-phase pipeline with independent error boundaries: (1) write handoff files (task status, explorer results), (2) determine outcome with retry for race conditions, (3a) store insights, (3b) apply causal feedback, (3c) log diagnostics, (3d) create provenance edges (`led_to` from causal parents to newly stored child), (3e) archive to session_log with orchestrator context. Each sub-phase failing does not block the others.

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
| **Helix** | Hybrid (vector + FTS5 + graph, RRF fusion) | Yes | EMA + **weighted** causal filtering + asymmetric erosion/decay + **generality-modulated decay** + **velocity** + prune + **cross-session synthesis** | Yes | Yes |

**Closed feedback loop.** Most memory systems are write-only (CLAUDE.md, auto-memory) or perform write-time curation where an LLM decides what to keep (Mem0). Neither approach adjusts memory quality based on whether the memory actually helped. Research on accumulation-based systems confirms sustained performance decline from memory inflation ([Memory-R1](https://arxiv.org/abs/2508.19828), [MEM1](https://arxiv.org/abs/2506.15841)). Helix updates each insight's effectiveness via EMA after every task outcome, with asymmetric erosion ensuring bad insights do not self-rehabilitate without positive causal evidence.

**Causal attribution.** Among production systems, none distinguish "this memory was present in the agent's context" from "this memory was relevant to what the agent did." Among research systems, only [Reflexion](https://arxiv.org/abs/2303.11366) (verbal self-reflection), [ExpeL](https://arxiv.org/abs/2308.10144) (trajectory comparison), and Memory-R1 (RL reward signal) approach this. Helix implements explicit per-memory causal similarity: the query embedding from injection is carried through a sideband file and compared against the task context via vectorized dot product (threshold 0.50). Only causally relevant insights receive full EMA feedback; non-causal ones erode toward neutral.

**Graph structure.** Zep/Graphiti and engram use graph-based retrieval, but their graphs serve different purposes: Graphiti models entity-relationship triples extracted by LLM, engram uses a fixed memory topology. Helix's graph is emergent—`similar` edges form automatically from embedding proximity during storage (zero LLM calls), `led_to` edges capture provenance when one insight causally spawns another. This connects the feedback loop to structure: the graph encodes which insights are related and which spawned new knowledge, enabling 1-hop expansion during recall that surfaces context invisible to keyword and vector search alone.

**Orchestration integration.** Memory is not a separate service queried on demand. It is woven into the explore/plan/build lifecycle at two granularities: the RECALL phase provides strategic context with graph expansion (constraints, risk areas, exploration targets) that shapes decomposition, while the SubagentStart hook provides tactical context that shapes execution. Cross-agent diversity is maintained via sideband files, ensuring parallel builders receive different insights.

**Research alignment.** Helix's scoring formula (`relevance x effectiveness x recency`) parallels the composite retrieval score from [Generative Agents](https://arxiv.org/abs/2304.03442). Its extraction pipeline aligns with ExpeL's trajectory-based insight extraction. The emerging RL frontier ([Memory-R1](https://arxiv.org/abs/2508.19828), [MEM1](https://arxiv.org/abs/2506.15841), [mem-agent](https://huggingface.co/blog/driaforall/mem-agent-blog)) trains agents to learn *when* to remember through reinforcement — a natural next step beyond helix's rule-based feedback model.

## Local-First

Everything stays on your machine:
- SQLite database at `.helix/helix.db` (WAL mode)
- Sideband files at `.helix/injected/` (consume-once)
- Explorer results at `.helix/explorer-results/`
- Task status at `.helix/task-status.jsonl`
- Recall synthesis at `.helix/recall_synthesis.json` (session-scoped)
- Session archive in `.helix/helix.db` (`session_log` table, persistent)
- No external API keys for memory services
- No data leaving your system
- No usage fees

## Tuning Constants

Every scoring constant has a principled basis. Cross-referenced against reinforcement learning theory, prospect theory, cognitive science, spaced repetition research, and production IR systems.

| Constant | Value | Basis |
|---|---|---|
| `RRF_K` | 60 | Cormack, Clarke & Buettcher (2009) SIGIR. Tested k=1-1000 across TREC benchmarks; k=60 most robust. Adopted by Elasticsearch, OpenSearch, Azure AI Search as default. |
| `FEEDBACK_EMA_WEIGHT` | 0.2 | Sutton & Barto (2018) Ch. 2: constant-alpha EMA for non-stationary bandits; 0.1-0.2 is the practical range. Effective window = `2/α - 1 = 9` feedback events. Appropriate for sparse feedback (few uses per project lifecycle). |
| `EROSION_RATE` | 0.09 | Loss-aversion calibrated. Kahneman & Tversky (1992): λ=2.25. Erosion (non-causal, weaker evidence) should relate to EMA weight (causal, stronger evidence) via: `EMA_WEIGHT / λ ≈ 0.2 / 2.25 ≈ 0.089`. Baumeister et al. (2001): "bad is stronger than good" — non-causal erosion is intentionally weaker than causal learning. |
| `DECAY_RATE` | 0.1 | Per-session exponential: `new = eff × 0.9 + 0.5 × 0.1`. Anderson & Schooler (1991) power-law forgetting; per-session exponential produces similar shape with irregular spacing. Asymptotic to 0.5 (neutral). |
| `HOP_DISCOUNT` | 0.7 | PageRank damping d=0.85 (Brin & Page 1998) is the upper bound — link traversal preserves ~85% of authority. Collins & Loftus (1975) spreading activation: single-hop semantic neighbors retain substantial relevance. 0.7 balances signal preservation against noise; at 0.5 (previous), graph-expanded insights barely survived the min_relevance gate. |
| `RECENCY_DECAY_PER_DAY` | 0.003 | Collaborative filtering literature: 150-day half-life optimal for preference data (Ding & Li 2005, CIKM). At 0.003/day: 231-day half-life, conservative for semantic/procedural knowledge (longer-lived than episodic memory per Ebbinghaus 1885, confirmed by Murre & Dros 2015 R²=98.8%). |
| `RECENCY_FLOOR` | 0.85 | 15% maximum lifetime penalty. Floor reached at ~50 days. Creates three temporal tiers: fresh (0-15d, <5% penalty), aging (15-50d, 5-15%), dormant (50d+, capped at 15%). Ebbinghaus-inspired shape: rapid initial decay, then plateau. Protects evergreen strategic knowledge. |
| `CAUSAL_ADJUSTMENT_FLOOR` | 0.33 | At-chance base rate for `CAUSAL_MIN_USES=3`. With 0 causal hits out of 3 uses, the floor matches the probability of one hit by chance (1/3=0.333). Eliminates the discontinuity between 0 hits and 1 hit that existed at the previous 0.3 floor. Clean progression: 0/3→0.33, 1/3→0.33, 2/3→0.67, 3/3→1.0. |
| `DUPLICATE_THRESHOLD` | 0.85 | Standard for embedding-based dedup; corresponds to paraphrase-level similarity on STS benchmarks with arctic-embed-m-v1.5. |
| `RELATED_THRESHOLD` | 0.60 | Boundary between "topically related" (0.35-0.60) and "semantically similar" (0.60-0.85) in arctic-embed-m-v1.5's characteristic score distribution. Model-dependent engineering choice. |
| `MAX_AUTOLINK_EDGES` | 5 | Small-world network theory (Watts & Strogatz 1998): average degree 4-8 produces short path lengths + high clustering. Dunbar (1992) innermost layer = 5 closest associates. At 100 insights, yields average degree ~10 (within small-world regime). |
| `CAUSAL_SIMILARITY_THRESHOLD` | 0.50 | Attribution gate for feedback. Above auto-link threshold (0.60 is content-content; 0.50 is query-document with asymmetric encoding, naturally lower scores). Top 20-30% of insight-query pairs pass at this threshold. Raised from 0.40 for tighter causal attribution. |
| `CAUSAL_WEIGHT_RAMP` | 0.50 | Weight normalization for similarity-proportional feedback. Linear ramp: 0.0 at threshold (sim=0.50), 1.0 at perfect match (sim=1.0). Replaces binary attribution. |
| `VELOCITY_PER_USE` | 0.02 | Score boost per recent causal feedback event. 5 recent uses = 10% boost. |
| `VELOCITY_CAP` | 0.10 | Maximum velocity boost. Prevents runaway boosting from very active insights. |
| `VELOCITY_WINDOW_DAYS` | 14 | Window for "recent" usage. Velocity resets via decay() for events older than this. |
| `GENERALITY_SPREAD_CAP` | 0.30 | Context spread at which an insight is considered "fully general" (principle-level). |
| `GENERALITY_DECAY_DISCOUNT` | 0.50 | Maximum decay rate reduction for general insights. Principles decay at 0.05/session vs 0.1/session for observations. |
| `GENERALITY_MIN_SPREAD` | 0.05 | Minimum context_spread for generality modulation to apply. Below this, insufficient diversity data. |
| `CLUSTER_SIM_THRESHOLD` | 0.60 | Single-linkage merge threshold for cross-session summary clustering. |
| `MIN_CLUSTER_CONFIDENCE` | 1.5 | `tightness x sqrt(count)` floor for synthesis candidates. Filters weak patterns. |

### References

- Cormack, Clarke & Buettcher (2009). "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods." *SIGIR*.
- Sutton & Barto (2018). *Reinforcement Learning: An Introduction*, 2nd ed. Ch. 2.
- Kahneman & Tversky (1992). "Advances in Prospect Theory." *J. Risk and Uncertainty* 5(4). Loss aversion λ=2.25.
- Baumeister et al. (2001). "Bad is Stronger than Good." *Review of General Psychology* 5(4).
- Brin & Page (1998). "The Anatomy of a Large-Scale Hypertextual Web Search Engine." PageRank d=0.85.
- Collins & Loftus (1975). "A Spreading-Activation Theory of Semantic Processing." *Psychological Review* 82(6).
- Ebbinghaus (1885). *Uber das Gedachtnis*.
- Murre & Dros (2015). "Replication and Analysis of Ebbinghaus' Forgetting Curve." *PLOS ONE* 10(7).
- Anderson & Schooler (1991). "Reflections of the Environment in Memory." *Psychological Science* 2(6).
- Ding & Li (2005). "Time Weight Collaborative Filtering." *CIKM*. 150-day half-life.
- Watts & Strogatz (1998). "Collective dynamics of 'small-world' networks." *Nature* 393.
- Dunbar (1992). "Neocortex size as a constraint on group size in primates." *J. Human Evolution* 22(6).

## Technical Reference

For implementation details—agent contracts, database schema, CLI reference, scoring formulas, tuning constants—see [docs/HELIX_OVERVIEW.md](./docs/HELIX_OVERVIEW.md).
