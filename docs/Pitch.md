# Helix: A Self-Learning Orchestrator for Claude Code

Every agent memory system we looked at has the same blind spot: they store knowledge, but they never find out if it helped.

CLAUDE.md is a flat file — everything in, no feedback, no search. Mem0 asks an LLM at write time whether something matters, but never checks whether it was right. Engram, kore, and ember-mcp decay memories on timers, treating a memory that saved your build and one that tanked it identically. The research literature backs this up: accumulation-based systems show flat or declining performance as memory grows. Storing everything and hoping relevance emerges is not a strategy.

The deeper problem: **presence is not causation.** A memory sitting in the agent's context during a success is not the same as a memory that caused the success. Without distinguishing the two, you reward bystanders and punish the innocent. Every feedback system built on "this memory was present" is learning noise.

---

Helix closes this gap. It's a Claude Code plugin — an orchestrator with integrated memory where **insights must prove their worth through demonstrated usefulness.**

Two loops, interlocked:

**The orchestration loop** runs within a session. `/helix <objective>` fires six phases: recall accumulated knowledge, explore the codebase (informed by what memory says matters), plan a task DAG (constrained by proven insights, cautious around risky ones), build in parallel waves with stall recovery, learn from the session's outcomes with the user, and complete. Memory shapes every phase — it's not bolted on, it's woven in.

**The learning loop** runs automatically across sessions via hooks. When a builder spawns, the system injects relevant insights into its prompt — with tracked names and a saved embedding of the query context. When the builder finishes, a hook fires. It compares each injected insight's embedding against what the builder actually worked on. Only insights semantically relevant to the task receive causal credit — **proportional to their similarity strength**. A barely-relevant insight gets near-zero feedback; a strongly-relevant one gets full EMA update. The rest were bystanders — they erode toward neutral.

This attribution is conservative by design. Empty context, failed embedding, any exception — four independent code paths return "no feedback" rather than risk wrong attribution. The system would rather learn nothing than learn the wrong thing.

Over time, insights that consistently contribute rise in ranking. Insights that tag along without helping decay and eventually prune. The scoring formula modulates retrieval by proven effectiveness and recency — bad insights get demoted but not hidden (they still need to be findable for negative feedback to work). After enough uses with zero causal hits, an insight's adjusted effectiveness drops below the prune threshold and it gets deleted.

Memories earn their place or they leave. The system gets better over time, not worse.

Three feedback timescales interlock. The **fast loop** runs per-task: weighted causal attribution, velocity-boosted scoring for active insights, generality tracking that distinguishes principles (decay slowly) from observations (decay normally). The **medium loop** persists orchestrator decisions as structured files and captures CONSTRAINTS/RISK_AREAS from the parent transcript at every subagent spawn. The **slow loop** runs at session end: embedding-based clustering of failure summaries across sessions produces new insights that enter the fast loop and must prove themselves like anything else. A content security scanner gates storage against prompt injection and credential leaks.

---

**Retrieval is hybrid** — vector similarity for semantic matching, FTS5 keyword search for exact technical terms (error codes, library names) that embeddings tend to underweight, fused via Reciprocal Rank Fusion. A knowledge graph forms automatically: insights link to similar neighbors at storage time (zero LLM calls), and provenance edges track when one insight spawns another. Recall traverses these edges by default, surfacing context that neither keyword nor vector search would find alone. Graph analytics (connected components, articulation points, density) give the orchestrator structural signals about its own knowledge: dense clusters, novel isolates, cross-cutting bridges.

**The LEARN phase is human-in-the-loop.** The orchestrator sees cross-task patterns that individual builders can't — convergent failures, ordering issues, shared blockers. It presents hypotheses to the user with quoted error text, specific file paths, and evidence-grounded options. The user's domain knowledge enters the system as first-class insights. These skip the normal dedup merge — a human correction of an existing insight should never be silently absorbed into the thing it's correcting. The feedback loop evaluates both versions independently and lets the evidence decide.

**The orchestrator is a markdown file**, not a state machine. Prose-driven orchestration, three agent types (sonnet explorers, opus planners, opus builders), minimal scaffolding. The architecture is Claude-native: SQLite + numpy + arctic-embed, zero daemons, zero cloud, single-file database. 378 tests, ~3,800 lines of Python across 15 modules.

---

We surveyed 30+ systems across the Claude Code plugin ecosystem, MCP memory servers, and the research frontier. The closest analog is MemRL/Tempera (Q-value utility tracking), which has stronger theoretical foundations but credits the entire retrieved set uniformly — no per-memory causal distinction. Helix is the only production system that closes the loop from task outcome to memory quality through per-insight causal attribution with similarity-proportional weighting, multi-timescale feedback (velocity, generality, cross-session synthesis), and structural self-awareness via graph analytics.