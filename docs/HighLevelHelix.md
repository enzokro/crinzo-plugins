# How Helix Works

Three systems, interlocked. Memory that learns. Orchestration that listens. Hooks that close the loop.

---

## The Problem

Agent memory systems store things. That's the easy part. The hard part: knowing whether what you stored was any good.

Most systems dodge this entirely. CLAUDE.md is a flat file — everything in, nothing out, no feedback. Mem0 asks an LLM at write time whether something is worth keeping, but never checks back. Engram decays memories on a timer, treating a memory that saved your build and a memory that crashed it identically. The research literature confirms this goes badly: accumulation-based systems show flat or declining performance as memories pile up ([Memory-R1](https://arxiv.org/abs/2508.19828), [Experience-Following Behavior](https://arxiv.org/abs/2505.16067)).

The fundamental issue: **presence is not causation**. A memory that happened to be in the agent's context during a success is not the same as a memory that caused the success. Without distinguishing the two, feedback systems reward bystanders and punish the innocent.

## The Architecture

Helix has three loops. One runs within a session. Another runs automatically via hooks. A third runs across sessions, synthesizing patterns from accumulated history. They share a memory system, and the places where they meet are where the learning happens.

### Loop 1: Orchestration

A single session. User says `/helix <objective>`, and six phases run:

```
RECALL ──> EXPLORE ──> PLAN ──> BUILD ──> LEARN ──> COMPLETE
                                  │                    │
                                  └── waves ───────────┘
```

**RECALL** queries memory before anything else happens. Not just "find relevant stuff" — the orchestrator classifies recalled insights by their track record. Proven insights (effectiveness >= 0.70) become hard constraints on the plan. Risky ones (< 0.40, or tagged `derived`/`failure`) flag areas for extra caution. The planner receives both, and the distinction matters: constraints restrict decomposition, risk areas expand verification.

**EXPLORE** maps the codebase. Sonnet explorers run in parallel, each covering a partition. Recalled insights shape where they look — if memory says "config/secrets.py has caused issues," the explorer covering config/ prioritizes that file.

**PLAN** decomposes into a task DAG. Opus planner. Data-flow dependencies only — "makes sense to do first" is not a dependency. Each task gets a concrete verify command, relevant files, and a size target (1-3 files). The plan respects constraints from memory and accounts for risk areas.

**BUILD** executes in waves. Up to 6 opus builders per wave, each with injected insights from memory. When a builder finishes — DELIVERED, BLOCKED, or PARTIAL — the hooks fire automatically. PARTIAL outcomes fold remaining work into the next wave. Stalls trigger recovery: recall what's known about the blocked area, then skip / re-plan / tighten verification / abort after 3+ attempts.

**LEARN** is not automated. The orchestrator observes cross-task patterns that individual builders cannot see — convergent failures, ordering issues, shared blockers. It presents hypotheses to the user with actual error text, specific file paths, and evidence-grounded options. The user confirms, corrects, or provides their own answer. The insight gets stored with a `user-provided` tag that protects it from being silently merged with existing memories.

### Loop 2: Learning

This one is invisible. It runs inside the hooks — SubagentStart and SubagentStop — on every builder and planner invocation. No user action required.

```
INJECT ──> EXECUTE ──> ATTRIBUTE ──> FEEDBACK
  │                                      │
  └────── future recalls rank by ────────┘
          proven effectiveness
```

**INJECT**: Before a builder starts, the SubagentStart hook recalls up to 3 insights for its task. Each insight goes into the prompt with its name tracked. The hook also writes a sideband file — a small JSON artifact carrying the insight names, the query objective, and the pre-computed query embedding. This sideband file is the bridge between injection and attribution.

**EXECUTE**: The builder does its work. Produces DELIVERED, BLOCKED, or PARTIAL.

**ATTRIBUTE**: After the builder finishes, the SubagentStop hook reads the sideband file. It fetches the stored embedding for each injected insight and computes cosine similarity against the task context (vectorized matmul, single operation). Only insights with similarity >= 0.50 to what the builder actually worked on receive causal credit. The rest were bystanders.

**FEEDBACK**: Causally relevant insights get a **weighted** EMA update — `new_eff = old * (1 - 0.2*w) + outcome * 0.2*w` — where `w` scales linearly from 0.0 at the similarity threshold (0.50) to 1.0 at perfect match. A barely-causal insight gets near-zero update; a strongly-causal one gets full EMA. DELIVERED pushes toward 1.0; BLOCKED pushes toward 0.0. PARTIAL outcomes (0.3) produce feedback between delivered and blocked — partial success is a weaker positive signal. Non-causal insights erode 9% toward neutral (0.5), but only if they're currently above 0.5. Below-neutral insights don't self-rehabilitate — that's intentional. Bad knowledge stays bad until positive causal evidence says otherwise.

The conservative design is load-bearing. Four separate code paths return "no feedback" (empty list) rather than risk wrong attribution: empty names, empty context, embedding failure, any exception. The system would rather learn nothing than learn the wrong thing.

### Loop 3: Cross-Session Synthesis

This one runs at session end. It's the slowest loop — synthesizing patterns that no single session could see.

```
SESSION_LOG ──> CLUSTER ──> COMPARE ──> STORE/REINFORCE
    │                                        │
    └──── future sessions start smarter ─────┘
```

The session archive records every subagent completion: agent type, outcome, summary, orchestrator constraints. At session end, after decay and prune, `synthesize_session()` reads recent entries and clusters failure summaries by embedding similarity (agglomerative, threshold 0.60).

Tight clusters with sufficient evidence (confidence >= 1.5) become candidate insights. If an existing insight already covers the pattern, it receives reinforcement feedback. If not, a new insight is stored at effectiveness 0.45 — above derived (0.35) but below neutral (0.5). It must prove itself through the fast loop like anything else.

The slow loop feeds the fast loop: synthesized insights enter the normal recall/inject/feedback cycle. Insights that consistently contribute rise. Those that don't, erode and prune. No special treatment — the same selective pressure that governs everything.

### Where the Loops Meet

The orchestration loop writes what the learning loop reads (task outcomes trigger hooks). The learning loop writes what the orchestration loop reads (effectiveness scores shape future recall). Three interlock points:

1. **Memory shapes orchestration.** RECALL pulls insights ranked by `rrf_score * (0.5 + 0.5 * effectiveness) * recency`. An insight that has been injected 20 times with zero causal hits gets its effectiveness scaled down to `eff * 0.33` — it falls out of the top results and eventually prunes.

2. **Orchestration shapes memory.** The LEARN phase produces user-validated insights. These skip dedup merge (a human correction of an existing insight should not be silently absorbed into the thing it's correcting). They enter the feedback loop independently and must prove themselves.

3. **Session history shapes synthesis.** The slow loop reads what the fast loop wrote (session_log entries from SubagentStop). The insights it produces enter the fast loop's recall pool. Three timescales — per-task, per-session, cross-session — each feeding the next.

---

## The Memory System

SQLite database, arctic-embed-m-v1.5 embeddings (768-dim), numpy for vectorized similarity. No daemons, no containers, no cloud. A `.venv` with two dependencies. Schema v15. Three tables: insight (14 columns), insight_edges (graph), session_log (archive). Two FTS5 indexes. ~3,800 lines of Python, 378 tests.

### How Recall Works

Hybrid retrieval. Two ranking systems, fused:

1. **Vector**: embed the query in asymmetric mode, dot product against all insight embeddings, sort by cosine similarity.
2. **Keyword**: FTS5 MATCH on insight content and tags, sort by BM25. This catches exact technical terms — error codes, library names, CLI flags — that vector similarity tends to underweight.
3. **RRF fusion**: `score = 1/(60 + vec_rank) + 1/(60 + fts_rank)`. An insight ranked high in both lists gets a strong boost. One ranked high in only one still surfaces. K=60 is the [SIGIR 2009 standard](https://dl.acm.org/doi/10.1145/1571941.1572114).
4. **Scoring**: `rrf_score * (0.5 + 0.5 * effectiveness) * recency * (1 + velocity_boost)`. Effectiveness modulates ranking — proven insights score higher — but even the worst insight only gets halved (0.5 floor), never hidden. It still needs to be findable for negative feedback to work.
5. **Graph expansion**: Top results' neighbors via `similar` and `led_to` edges (1-hop, score discounted by 0.7). Surfaces related context that neither keyword nor vector search would find alone.

A `min_relevance` gate (default 0.35 cosine) applies to everything. FTS5 keyword matches cannot bypass it. An insight about "JWT" will not contaminate a recall about "database migrations" just because both contain the word "token."

### How Insights Accumulate (And Don't)

Six layers prevent unbounded growth:

1. **Semantic dedup** at write time. Cosine >= 0.85 triggers merge. Longer content replaces shorter; low-effectiveness content gets overwritten by fresh observations. But user-provided insights skip this entirely — human judgment is never silently merged.

2. **Asymmetric decay.** Insights unused for 30+ days drift toward neutral (0.5). But only above-0.5 insights decay. Bad ones don't rehabilitate from neglect.

3. **Asymmetric erosion.** Non-causally-attributed insights erode 9% toward neutral per feedback event. Again, only above-0.5. The rate (0.09) is calibrated via [Kahneman & Tversky's loss aversion ratio](https://doi.org/10.1007/BF00122574) (λ=2.25): `EMA_weight / λ = 0.2 / 2.25 ≈ 0.089`.

4. **Causal-adjusted pruning.** After 3+ uses, effectiveness is scaled by `max(0.33, causal_hits / use_count)`. An insight with raw effectiveness 0.50 but zero causal hits in 20 uses adjusts to `0.50 * 0.33 = 0.165` — below the prune threshold of 0.25.

5. **Ghost cleanup.** Valid-embedding insights with zero use_count after 60 days are deleted. Catches insights that were stored but never relevant enough to surface.

6. **Knowledge generality.** Over time, the system tracks the semantic diversity of contexts where an insight proves causally useful (Welford's algorithm on cosine space). High diversity = principle — decays at half the normal rate. Low diversity = observation — decays normally. The system discovers what kind of knowledge each insight is through measured behavior, not classification.

### The Graph

Insights form a lightweight knowledge graph. Two edge types:

**`similar`** edges form automatically during `store()`. The dedup similarity computation is already done; candidates with 0.60 <= similarity < 0.85 get linked as neighbors. Top 5 per insert. Zero extra cost — it reuses the vector already in hand.

**`led_to`** edges form during extraction. When a BLOCKED outcome generates a derived insight, and the causal filter identifies which parent insights were relevant, provenance edges connect parents to child. The graph records which knowledge spawned which.

Recall traverses these edges by default (`graph_hops=1`). The LEARN phase can check provenance chains — if an injected insight descends from a low-effectiveness lineage, the orchestrator flags it as a potential error propagation vector.

---

## The Hooks

Four lifecycle hooks make the whole thing automatic. The user invokes `/helix` and the learning machinery runs in the background.

| Hook | Fires when | What it does |
|------|-----------|-------------|
| **SessionStart** | Session opens | Bootstrap venv, persist env, warmup embeddings, report memory health |
| **SubagentStart** | Builder/planner spawns | Recall insights, write sideband, inject context |
| **SubagentStop** | Any helix agent finishes | Extract outcome, store insights, causal feedback, provenance edges |
| **SessionEnd** | Session closes | Decay dormant insights, prune low performers, **cross-session synthesis**, cleanup |

The sideband file is the key coordination artifact. Written by SubagentStart (injection), read-and-deleted by SubagentStop (extraction). It carries three things: the insight names that were injected, the exact query objective, and the pre-computed query embedding (base64). This embedding is what makes causal attribution cheap — instead of re-embedding during extraction, the sideband passes the vector directly.

Cross-agent diversity works through the sideband too. When parallel builders spawn, each SubagentStart hook reads existing sideband files from sibling agents to see what was already injected. Those names get suppressed in the recall, so later builders receive different insights. No shared process memory needed — just files on disk.

**Orchestrator state capture.** SubagentStart doesn't just extract the task objective — it also captures CONSTRAINTS and RISK_AREAS sections from the orchestrator's prompt via regex. These flow through the sideband file and into session_log archival, giving the slow loop access to orchestrator-level reasoning, not just agent-level outcomes.

SubagentStop has five independent error boundaries: (1) handoff files, (2) outcome determination, (3a) store insights, (3b) causal feedback, (3c) logging, (3d) provenance edges, (3e) session_log archival with orchestrator context. A failure in one does not prevent the others. The system degrades rather than crashes.

---

## Two Levels of Memory Injection

Memory enters the orchestration at two distinct points, each serving a different purpose:

**Strategic** (RECALL phase): The orchestrator calls `strategic_recall()` with broad parameters — limit=15, min_relevance=0.30, graph_hops=1. This is a wide net. The results shape *how to decompose the problem*: what constraints to respect, what risks to flag, where to explore beyond the obvious.

**Tactical** (SubagentStart hook): The hook calls `recall()` with narrow parameters — limit=3, min_relevance=0.35, graph_hops=1. This is a focused injection. The results shape *how to execute a specific task*: patterns to follow, pitfalls to avoid.

The hook detects whether the orchestrator already injected insights into the prompt (via an `INSIGHTS_HEADER` marker). If it did, the hook writes the sideband file but skips injecting additional context — no duplication.

---

## What Makes This Different

The diagram tells the story. Every other production memory system has an open loop somewhere — store without feedback, feedback without causation, causation without asymmetry. Helix closes all three:

```
store → recall → inject(tracked names) → execute
                                            │
                        observe outcome ────┘
                            │
                    attribute causally (cosine >= 0.50)
                            │
                ┌───────────┴───────────┐
                │                       │
         causal: EMA update      non-causal: erode
         use_count++             (above 0.5 only)
         causal_hits++
                │                       │
                └───────────┬───────────┘
                            │
              read-time adjustment:
              eff * max(0.33, causal_hits/use_count)
                            │
                     prune if < 0.25
                     after 3+ uses
```

The loop is closed, causal, and asymmetric. Memories earn their place or they leave.

Three additional dimensions that no other production system combines:

**Multi-timescale learning.** The fast loop (per-task feedback) is augmented by velocity tracking (14-day usage spikes boost scoring), generality tracking (context diversity modulates decay), and cross-session synthesis (embedding-clustered failure patterns become new insights). Each timescale feeds the others.

**Content security.** A scanner gates `store()` with 14 regex patterns: prompt injection, credential leaks (generic relaxed for prescriptive insights, provider-specific never relaxed), invisible unicode, exfiltration. The system recognizes its own output format and exempts it from false-positive credential checks.

**Structural self-awareness.** Graph analytics compute connected components, articulation points (bridge insights), density, and isolates over the recalled subgraph. The orchestrator receives a KNOWLEDGE_TOPOLOGY block: dense clusters = well-understood domains, isolates = novel knowledge needing validation, bridges = cross-cutting concerns worth verifying carefully.
