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
