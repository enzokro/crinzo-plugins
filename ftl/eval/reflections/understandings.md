# Understandings

Beliefs with explicit uncertainty. Updated via reflection.

---

## L001: Structural framing > policy prohibition

**Belief**: Framing constraints as structural impossibilities (category errors) prevents violations more reliably than imperative rules (DO NOT).

**Confidence**: 8/10

**Evidence**: v10 had 4+ prohibitions, 5 violations. v12 had 1 category error framing, 0 violations.

**Mechanism**: Negation requires holding the forbidden action in mind while suppressing it. Category framing excludes the action from consideration entirely.

**Generalizes to**: Any constraint on AI behavior. "X is incoherent in context Y" > "NEVER do X in context Y".

**Would update if**: Category framing failed where prohibition succeeded.

---

## L002: Main session contains spawn authority

**Belief**: The orchestrator session (non-agent JSONL) is the authoritative source for spawn order and parent-child relationships. Agent logs are children; the main session is the parent.

**Confidence**: 9/10

**Evidence**: anki-v12 main session contains 14 Task tool calls matching all 14 spawned agents in exact order.

**Mechanism**: FTL orchestrator issues Task tool calls; each spawns an agent with its own log. The orchestrator log is the call stack; agent logs are the called functions.

**Generalizes to**: Any multi-agent system where a coordinator spawns workers.

**Would update if**: Found spawn relationships that don't originate from main session Task calls.

---

## L003: Task identity > temporal proxy

**Belief**: Match spawn intent to agent execution by task_id, not file mtime. Temporal proxies fail when files are written in bursts (all mtimes within milliseconds).

**Confidence**: 9/10

**Evidence**: anki-v12 agent logs all have mtimes within 11ms window. Mtime-based matching assigned wrong spawn_order. Task-based matching achieved 14/14 correct matches.

**Mechanism**: File mtimes reflect when logs are collected/written, not when agents were spawned. Task_id is semantically stable; mtime is incidental.

**Generalizes to**: Any matching problem where temporal ordering is unreliable. Prefer semantic identifiers over temporal proxies.

**Would update if**: Found scenarios where task_id is ambiguous but temporal ordering is reliable.

---

## L004: Prompt content > file patterns for task assignment

**Belief**: Extract agent task assignment from prompt content, not from file read patterns. First_reads indicate context gathering, not task assignment.

**Confidence**: 9/10

**Evidence**: Routers read `002_card-crud-routes_complete.md` for context while working on task 005. Prompt-based extraction (Task: NNN, Workspace:...NNN_) correctly identifies 12/12 task assignments.

**Mechanism**: Agents read completed task files for precedent/context. The prompt contains the authoritative task assignment; file reads are inputs to reasoning.

**Generalizes to**: Any agent log analysis where behavior (file reads) differs from assignment (prompt).

**Would update if**: Found agents whose prompt doesn't contain task assignment but file patterns are reliable.

---

## L005: Single decision point > accumulated rules

**Belief**: Protocols with one clear decision point outperform protocols with accumulated conditional rules. "Ask one question, then branch" beats "check this list of conditions."

**Confidence**: 9/10

**Evidence**: v22 had 4+ overlapping sections per protocol, agents executed contradictory paths (+6.5% regression). v23 refactored to single decision point per agent (-35% improvement).

**Mechanism**: Multiple rules require holding all conditions in mind simultaneously. Single decision creates clear cognitive fork - the agent commits to one path.

**Generalizes to**: Any multi-step AI workflow. Prefer "if X then A else B" over "consider X, Y, Z, then decide."

**Would update if**: Found scenarios where accumulated rules outperformed single decision.

---

## L006: First thought reveals cognitive state

**Belief**: An agent's first reasoning statement predicts efficiency. "I have a clear picture" → efficient. "Let me look at X to understand" → expensive.

**Confidence**: 8/10

**Evidence**: v21-v24 builders. Efficient runs (53K) start with "I have a clear picture. I'll implement X." Expensive runs (211K+) start with "Let me look at Y to understand."

**Mechanism**: The first thought reflects whether the agent has sufficient context. Exploration-first language signals missing information that will cost tokens to acquire.

**Generalizes to**: Any agent monitoring. First-thought classification could predict token cost before execution completes.

**Would update if**: Found efficient runs that started with exploration language.

---

## L007: Verification coherence prevents cascading failures

**Belief**: Each task's Verify command must be satisfiable using ONLY that task's Delta. Incoherent verification causes builders to debug upstream issues.

**Confidence**: 9/10

**Evidence**: v21 builder 003 hit 313K tokens. Planner specified `-k study` filter but tests were named `test_rating_*`. Builder spent 6+ tool calls renaming tests - a planner error.

**Mechanism**: Builders trust workspace. Incoherent verification creates impossible success conditions. Builder enters debugging spiral trying to fix non-local issues.

**Generalizes to**: Any task decomposition system. Verification must be locally satisfiable.

**Would update if**: Found builders that efficiently handled verification requiring cross-task changes.

---

## L008: Accumulated patches create contradictions

**Belief**: Incremental protocol patches eventually contradict each other. Full refactors outperform patch accumulation.

**Confidence**: 8/10

**Evidence**: v13→v21 accumulated "Pre-Cached Context", "Core Discipline", "Specification Complete Test", "Section 1 bash commands" in planner. v22 agents executed both "Skip Section 1" AND Section 1 (+6.5% regression).

**Mechanism**: Each patch addresses a symptom without considering prior patches. Contradictions emerge when patches target the same behavior from different angles.

**Generalizes to**: Any evolving instruction set. Periodic consolidation prevents contradiction accumulation.

**Would update if**: Found long-running patch series that maintained coherence.

---

## L009: Knowledge flows forward in sequential routing

**Belief**: Sequential task routing (one task at a time) enables knowledge propagation. Parallel routing loses cross-task learning.

**Confidence**: 7/10

**Evidence**: v24 Task 003 (151K) vs v23 Task 003 (224K). Both hit date-string-mismatch, but v24 had context from completed earlier tasks. Sequential routing reduced debugging by 32%.

**Mechanism**: Completed workspaces contain Delivered sections and Thinking Traces. Sequential routing lets later tasks inherit this knowledge.

**Generalizes to**: Multi-agent orchestration. Consider knowledge dependencies, not just task dependencies.

**Would update if**: Found parallel routing that achieved similar knowledge propagation.

---

## L010: Cross-run learning requires explicit memory

**Belief**: Without persistent memory, each run is de novo. Patterns discovered in run N are lost to run N+1 unless explicitly persisted and seeded.

**Confidence**: 9/10

**Evidence**: v23 discovered date-string-mismatch through painful debugging (70K+ tokens). v24 avoided it, but not because it "learned" - sequential routing happened to propagate context. v25 would hit it again without memory seeding.

**Mechanism**: LLM context is ephemeral. Cross-run learning requires: (1) extraction at run end, (2) persistence to storage, (3) seeding at run start.

**Generalizes to**: Any iterative AI system. Learning requires memory architecture, not just execution.

**Would update if**: Found implicit learning mechanisms that persisted without explicit memory.

---

## L011: Upfront seeding ≠ runtime prevention

**Belief**: Knowledge seeded at task start does not prevent debugging spirals discovered during execution. Runtime issues require runtime intervention.

**Confidence**: 8/10

**Evidence**: v23, v26, v28 all hit date-string-mismatch during Builder 003 despite different levels of upfront knowledge. v28 had full memory injection (prior_knowledge.md → session_context, planner) yet Builder 003 still hit 286K tokens with "The database stores dates as strings" discovery during test verification.

**Mechanism**: Upfront knowledge is consumed at task START. Runtime debugging spirals occur AFTER implementation when tests fail. By the time the builder discovers the issue, it's in debugging mode - the upfront context window has passed. The builder encounters the issue fresh through test failure, not through missing context.

**Generalizes to**: Any agent system with multi-phase execution. Knowledge timing matters. Planning-phase knowledge doesn't reach execution-phase failures.

**Would update if**: Found upfront seeding that successfully prevented a runtime debugging spiral.

---
