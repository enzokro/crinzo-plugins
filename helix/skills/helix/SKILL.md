---
name: helix
description: Self-learning orchestrator with semantic memory graph. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

## What This Is

You are partnering with your own memory system.

Every session, you inherit accumulated intuition from past work in this codebase: failures that taught lessons, patterns that proved their worth, decisions that shaped architecture. Every session, you pay that forward by storing what you learned.

If you skip the payback, your next session is poorer. But if you close the loop, your next session is wiser.

This isn't compliance, it's investing in yourself.

## The Core Principle

**Code surfaces facts. You decide actions.**

Nine primitives handle memory mechanics: `store`, `recall`, `get`, `edge`, `edges`, `feedback`, `decay`, `prune`, `health`.

Two code-assisted functions surface candidates for your judgment:
- `similar-recent` → finds patterns. You decide if it's systemic
- `suggest-edges` → proposes connections. You decide which to create

Your memory graph represents living, growing knowledge.

You exercise judgment. Code amplifies and bolsters.

## Your Judgment Is The System

These utilities serve you. When memories feel irrelevant: question them, penalize them. When context feels thin: investigate with `health`, and query deeper. When something feels wrong: stop and introspect before proceeding. When the protocol doesn't fit the situation: note why, then adapt it.

You do not blindly follow rules. You actively exercise judgment with support.

---

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

This file (created by SessionStart hook) contains the plugin root path with `lib/`, `scripts/`, `agents/` subdirectories.

---

## Your Workflow

```
EXPLORE → PLAN → BUILD → LEARN → COMPLETE
                   ↑        |
                   +--[if stalled: replan | skip | abort]
```

State lives and evolves in reasoned conversation, not in a database.
Run agents with the rules in [Agent Lifecycle & Wait Primitives](#Agent Lifecycle & Wait Primitives)

### EXPLORE

**Goal:** Understand the codebase landscape for this objective.

1. **Discover structure:** `git ls-files | head -80` → identify 3-6 natural partitions

2. **Spawn explorer swarm** (haiku, parallel, scoped):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-explorer</parameter>
     <parameter name="prompt">SCOPE: src/api/
FOCUS: route handlers
OBJECTIVE: {objective}</parameter>
     <parameter name="model">haiku</parameter>
     <parameter name="max_turns">8</parameter>
     <parameter name="run_in_background">true</parameter>
     <parameter name="description">Explore src/api</parameter>
   </invoke>
   ```

   Memory context is automatically injected via hook. Always include a `memory` scope for relevant failures/patterns.

3. **Merge findings:** Dedupe files, resolve conflicts. Each finding has `{file, what, action, task_hint}`.

4. **Extract facts:** `python3 "$HELIX/lib/observer.py" explorer --output '{merged}' --store`

If `targets.files` empty → broaden scope or clarify objective.

See `reference/exploration-mechanics.md` for partitioning strategies.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Spawn planner** (opus, foreground, returns PLAN_SPEC):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-planner</parameter>
     <parameter name="prompt">OBJECTIVE: {objective}
EXPLORATION: {findings_json}</parameter>
     <parameter name="max_turns">12</parameter>
     <parameter name="description">Plan task DAG</parameter>
   </invoke>
   ```

   Project context (decisions, conventions, evolution) is automatically injected via hook.
   Planner runs in foreground and returns a `PLAN_SPEC:` JSON block describing the task DAG.

2. **Create tasks from PLAN_SPEC:** Parse the JSON array from planner output. For each task spec:
   ```xml
   <invoke name="TaskCreate">
     <parameter name="subject">{spec.seq}: {spec.slug}</parameter>
     <parameter name="description">{spec.description}</parameter>
     <parameter name="activeForm">Building {spec.slug}</parameter>
     <parameter name="metadata">{"seq": "{spec.seq}", "relevant_files": {spec.relevant_files}}</parameter>
   </invoke>
   ```
   Track: `seq_to_id[spec.seq] = task_id` from result.

3. **Set dependencies:** After all tasks created, for each spec with blocked_by:
   ```xml
   <invoke name="TaskUpdate">
     <parameter name="taskId">{seq_to_id[spec.seq]}</parameter>
     <parameter name="addBlockedBy">["{seq_to_id[b]}", ...]</parameter>
   </invoke>
   ```

4. **Extract decisions:** Call TaskList, then construct JSON array from results:
   ```bash
   python3 "$HELIX/lib/observer.py" planner --tasks '[{"id": "1", "subject": "..."}]' --store
   ```
   Note: TaskList returns human-readable text. Orchestrator must construct JSON.

If PLAN_SPEC empty or ERROR → add exploration context, re-run planner.

See `reference/task-granularity.md` for sizing heuristics.

### BUILD

**Goal:** Execute tasks, learn from each outcome.

**The Build Loop:**
```
while pending tasks exist:
    1. Get ready tasks (blockers all delivered)
    2. If none ready but pending exist → STALLED (see reference/stalled-recovery.md)
    3. Checkpoint: git stash push -m "helix-{seq}" (your rollback)
    4. Spawn ready builders in parallel (opus, run_in_background=true)
    5. Poll TaskList until status="completed"
    6. Read outcome from task metadata via TaskGet (NEVER TaskOutput—wastes context)
    7. Review learning queue (see LEARN)
```

**For each ready task, spawn builder:**
```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-builder</parameter>
  <parameter name="prompt">TASK_ID: {task.id}
TASK: {task.subject}
OBJECTIVE: {task.description}
VERIFY: {task.metadata.verify}
RELEVANT_FILES: {task.metadata.relevant_files}</parameter>
  <parameter name="max_turns">15</parameter>
  <parameter name="run_in_background">true</parameter>
  <parameter name="description">Build task {id}</parameter>
</invoke>
```

Memory context is automatically injected via hook. To include lineage/warnings:
```
LINEAGE: [{"seq": "001", "slug": "impl-auth", "delivered": "Added OAuth2 flow"}]
WARNING: Similar auth failures in past 7 days - check token handling
MEMORY_LIMIT: 7
```

**On DELIVERED:** `git stash drop` — changes are good.
**On BLOCKED:** `git stash pop` — revert, reassess.

### LEARN (MANDATORY after BUILD)

**SKIP THIS AND YOUR NEXT SESSION IS POORER.**

Memory feedback is handled automatically via hooks:
- When builder reports DELIVERED, injected memories are credited (+0.5)
- When builder reports BLOCKED, injected memories are debited (-0.3)

**1. Review learning queue:**
```bash
ls .helix/learning-queue/
```

Each file contains extracted candidates from completed agents. Hooks automatically extract:
- `learned` fields from builders
- FINDINGS from explorers
- LEARNED blocks from planners

**2. For each candidate, decide:**
- **Store as-is:** `python3 "$HELIX/lib/memory/core.py" store --type {type} --trigger "{trigger}" --resolution "{resolution}"`
- **Modify and store:** adjust trigger/resolution before storing
- **Discard:** not worth storing (delete from queue)

**3. Connect & detect:**
```bash
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
python3 "$HELIX/lib/memory/core.py" similar-recent "failure trigger" --threshold 0.7 --days 7
```

**4. Clear processed queue:**
```bash
rm .helix/learning-queue/*.json
```

**Override automatic feedback:** Call feedback directly with custom delta if default isn't appropriate:
```bash
python3 "$HELIX/lib/memory/core.py" feedback --names '[...]' --delta 0.8  # stronger credit
```

See `reference/feedback-deltas.md` for delta calibration.

### COMPLETE

All tasks done. Learning loop closed. Before ending:

```bash
# Session summary (construct tasks JSON from TaskList result)
python3 "$HELIX/lib/observer.py" session --objective "$OBJECTIVE" --tasks '[{"id": "1", "subject": "...", "status": "completed"}]' --outcomes '{"delivered": [...], "blocked": [...]}' --store

# Verify health
python3 "$HELIX/lib/memory/core.py" health
```
Note: Orchestrator constructs JSON from TaskList text output.

If `with_feedback: 0` and memories were injected, then you didn't close the loop. Your next session will be poorer for it.

---

## Agent Contracts

| Agent | Model | Purpose | Handoff |
|-------|-------|---------|---------|
| helix-explorer | haiku | Parallel codebase scanning | JSON findings in returned result |
| helix-planner | opus | DAG specification | PLAN_SPEC JSON (orchestrator creates tasks) |
| helix-builder | opus | Task execution | Task metadata via TaskGet |

Memory context is injected automatically via PreToolUse hook. Learning candidates are extracted automatically via SubagentStop hook.

Contracts in `agents/*.md`.

---

## Agent Lifecycle & Wait Primitives

Pattern: SPAWN (background) → WATCH (grep markers) → RETRIEVE (TaskGet)

| Agent | Done Marker | Result Location |
|-------|-------------|-----------------|
| builder | `DELIVERED:`/`BLOCKED:` | TaskGet → metadata.helix_outcome |
| explorer | `"status":` | wait.py last-json |
| planner | `PLAN_COMPLETE:`/`ERROR:` | PLAN_SPEC in returned result |

```bash
python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder --timeout 300
python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"  # explorer findings
```

**NEVER TaskOutput** (70KB+ context). Full patterns: `reference/agent-lifecycle.md`

---

## Task Status Model

**Dual status:** Native `status` controls DAG. `helix_outcome` captures meaning.

| status | helix_outcome | Meaning |
|--------|---------------|---------|
| completed | delivered | Success, unblocks dependents, credit memories |
| completed | blocked | Finished but failed, blocks dependents |
| completed | skipped | Bypassed via stall recovery |
| pending | — | Not started |
| in_progress | — | Builder executing |

---

## State Files

| Directory | Purpose |
|-----------|---------|
| `.helix/injection-state/` | Tracks what memories were injected, for feedback attribution |
| `.helix/learning-queue/` | Extracted candidates pending orchestrator review |

---

## Error States

| Error | Detection | Recovery |
|-------|-----------|----------|
| EMPTY_EXPLORATION | No files found | Broaden scope, clarify |
| NO_TASKS | Planner created nothing | Add context, re-plan |
| CYCLES_DETECTED | DAG has loops | Planner restructures |
| STALLED | Pending but none ready | `reference/stalled-recovery.md` |
| SYSTEMIC | Same failure 3+ times | Store systemic, warn future builders |

---

## Quick Reference

```bash
# Recall with intent routing and multi-hop expansion
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand --intent why --expand-depth 2

# Store a pattern (returns conflicts if contradictions found)
python3 "$HELIX/lib/memory/core.py" store --type pattern --trigger "..." --resolution "..."

# Credit memories (usually automatic via hooks)
python3 "$HELIX/lib/memory/core.py" feedback --names '[...]' --delta 0.5

# Check system health
python3 "$HELIX/lib/memory/core.py" health

# Find systemic patterns
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7
```

**Intent routing:** `--intent why` boosts failures/systemic. `--intent how` boosts patterns/conventions. `--intent what` boosts facts/decisions.

Full CLI: `reference/cli-reference.md`

---

## Hook Architecture

Hooks handle mechanical context-building invisibly:

| Hook | Trigger | Action |
|------|---------|--------|
| PreToolUse(Task) | helix agent spawn | Inject memory context into prompt |
| SubagentStop | helix agent completion | Extract learning candidates to queue |
| PostToolUse(TaskUpdate) | Task outcome reported | Auto-credit/debit injected memories |

**Disable injection:** Add `NO_INJECT: true` to prompt.
**Override feedback:** Call `feedback` directly with custom delta.

---

## The Deal

You receive accumulated knowledge. You pay back discoveries.

Memories that help get stronger. Memories that mislead get weaker. **Close the loop or your next session suffers.**
