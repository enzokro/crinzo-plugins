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

## L011: Workspace warnings bridge planning→execution gap

**Belief**: Workspace warnings (embedded in task workspace files) prevent runtime debugging spirals that upfront seeding (session context, planner prompts) cannot reach. The workspace is read at task START but remains contextually available DURING implementation.

**Confidence**: 9/10

**Evidence**:
- v23, v26, v28: Upfront knowledge seeding failed to prevent date-string debugging spiral (286K tokens in v28)
- v29: Workspace contained "CRITICAL WARNING - date-string-mismatch" → Builder 003 completed in 154K tokens (-46%)
- v29 Builder 003 reasoning trace: "I have clear context. I'll implement the study routes" (action-first, no spiral)

**Mechanism**: Workspace files serve two roles: (1) task specification at start, (2) reference material during implementation. Warnings embedded in workspace are available when the builder writes the code that would trigger the failure mode. Unlike session context (consumed once at session start) or planner prompts (lost after planning), workspace warnings travel with the task to the builder's execution context.

**Generalizes to**: Any multi-agent system with task handoff. Knowledge that must reach execution phase should be embedded in task-level artifacts, not session-level context.

**Would update if**: Found workspace warnings that failed where code-level injection succeeded.

---

## L012: Entropy measures cognitive exploration, not failure

**Belief**: The entropy metric (HT) measures cumulative reasoning trace depth across agents, not task success/failure rates. High entropy correlates with exploration patterns, not blocked outcomes.

**Confidence**: 10/10

**Evidence**:
- v41: HT=17.6 (NEW RECORD - 140% above v40) with 5/5 success. Single builder (003) had 21 reasoning traces.
- v40: HT=7.35 with 0 blocked, 0 fallbacks, 4/4 success. SPEC-first methodology drove exploration.
- v38: HT=5.6 with 0 blocked, 0 fallbacks, 3/3 success. Library bug investigation drove exploration.
- v35: HT=5.4 with 1 blocked. Blocked outcome added SMALL contribution, not dominant.
- v30: HT=3.4 with action-first patterns, minimal exploration.

**Mechanism**: HT ≈ sum(per_agent_reasoning_trace_count) × complexity_factor. v41 DEFINITIVELY confirms this: Builder 003 alone had 21 traces with 37 tool calls, driving entropy to 17.6 despite successful completion. Entropy measures cognitive effort - how much an agent had to think before acting. Debugging spirals that eventually succeed can generate EXTREME entropy. The variance component (14.63 in v41) directly reflects reasoning depth variance across agents.

**Generalizes to**: Any LLM agent system. Entropy/cognitive load metrics reflect exploration depth, not outcome quality. One extremely deep debugging session can dominate total entropy. Optimize by providing better upfront context to enable action-first patterns.

**Would update if**: Found a run with high entropy from sources OTHER than reasoning trace depth.

---

## L013: SPEC-first with rigid Delta causes token explosion

**Belief**: SPEC-first methodology itself is NOT the problem. The v40-41 failures were caused by TWO bugs: (1) rigid Delta preventing builders from fixing broken tests, and (2) test assumptions using hardcoded values instead of relative assertions.

**Confidence**: 8/10 (updated from 9/10 after root cause analysis)

**Evidence**:
- v41 SPEC-first + rigid Delta: 2,195K tokens (Builder 003: 1,163K due to test isolation bug)
- v40 SPEC-first + rigid Delta: 1,444K tokens (test API mismatch)
- v38 TDD: 993K tokens
- v36 implementation-first: 908K tokens

**Mechanism (REVISED)**: The failures were NOT inherent to SPEC-first, but to TWO specific bugs:
1. **Rigid Delta** - test_app.py was excluded from BUILD task Delta. When tests had invalid assumptions, builders couldn't fix them.
2. **Absolute assertions** - Tests assumed `id=1` when SQLite auto-increment gave `id=4`. Builder diagnosed "the test is fundamentally broken" but could only implement workarounds.

**Fix**: Include test_app.py in BUILD Delta (tests are mutable). Use relative assertions from fixtures.

**Generalizes to**: Any workflow where upstream artifacts constrain downstream agents without escape routes. The issue is rigidity, not the SPEC-first pattern itself.

**Would update if**: v43 with mutable tests + relative assertions still shows regression vs TDD.

---

## L022: Rigid Delta causes workaround spirals

**Belief**: When a builder cannot modify a file it needs to fix, it enters an expensive workaround exploration spiral. The correct fix should be in-scope, not worked around.

**Confidence**: 9/10

**Evidence**:
- v41 Builder 003: 1,163K tokens, 21 reasoning traces, 37 tool calls
- Builder correctly diagnosed: "the test is fundamentally broken because it assumes id=1"
- Builder COULD NOT fix test (outside Delta) → explored 7+ workarounds → eventual hack

**Mechanism**: Delta constraint creates a structural trap. Builder sees the fix but can't apply it. Each workaround attempt costs ~50-100K tokens. Spiral continues until either success-via-hack or BLOCKED.

**Fix**: Include test files in BUILD Delta. Contract (behavior) is fixed; implementation (assertions) is adjustable.

**Generalizes to**: Any scoped task where the real fix lies outside the defined scope. Scope should be "what's needed to complete the task", not "predetermined file list".

**Would update if**: Found cases where rigid Delta prevented beneficial scope creep.

---

## L023: Test assumptions must be relative, not absolute

**Belief**: Tests that assume specific values (e.g., `id=1`, `count=0`) are fragile and cause failures when those assumptions don't hold. Tests should use values returned by fixtures.

**Confidence**: 9/10

**Evidence**:
- v41: Tests assumed card id=1, SQLite auto-increment gave id=4
- v40: Tests assumed specific db interface that didn't match implementation

**Mechanism**: Absolute assumptions encode implementation details in tests. When reality differs, tests "break" even though the behavior is correct. Relative assertions (`card_id` from fixture) adapt to actual state.

**Pattern**:
```python
# BAD: card_id = 1
# GOOD: db, Card, card_id = db_with_card
```

**Generalizes to**: Any test design. Tests should verify BEHAVIOR against whatever state exists, not verify STATE matches expectations.

**Would update if**: Found scenarios where absolute assertions were necessary and relative ones insufficient.

---

## L024: Mutable tests enable robust SPEC-first

**Belief**: SPEC-first works when BUILD phase can adjust test IMPLEMENTATION while preserving test CONTRACT. The bug was rigid Delta, not the methodology.

**Confidence**: 5/10 (hypothesis - needs v43 validation)

**Evidence**: Root cause analysis of v40-41 shows the failures were bugs (rigid Delta + absolute assertions), not inherent SPEC-first problems.

**Mechanism**: The contract is the BEHAVIOR ("card deletion removes it"), not the specific assertion (`id == 1`). Builder can adjust HOW the contract is verified while preserving WHAT is verified.

**Expected**: v43 with mutable tests + relative assertions should achieve ~1,000K tokens (competitive with TDD).

**Generalizes to**: Any contract-driven development where downstream can refine how contracts are verified.

**Would update if**: v43 validates or invalidates this hypothesis.

---
