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

1. **Inject what you already know:**
   ```bash
   python3 "$HELIX/lib/context.py" build-explorer-context --objective "$OBJECTIVE" --scope "$SCOPE"
   ```

2. **Discover structure:** `git ls-files | head -80` → identify 3-6 natural partitions

3. **Spawn explorer swarm** (haiku, parallel, scoped):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-explorer</parameter>
     <parameter name="prompt">SCOPE: src/api/
   FOCUS: route handlers
   ...</parameter>
     <parameter name="model">haiku</parameter>
     <parameter name="max_turns">8</parameter>
     <parameter name="run_in_background">true</parameter>
     <parameter name="description">Explore src/api</parameter>
   </invoke>
   ```
   Always include a `memory` scope for relevant failures/patterns.

4. **Merge findings:** Dedupe files, resolve conflicts. Each finding has `{file, what, action, task_hint}`.

5. **Extract facts:** `python3 "$HELIX/lib/observer.py" explorer --output '{merged}' --store`

If `targets.files` empty → broaden scope or clarify objective.

See `reference/exploration-mechanics.md` for partitioning strategies.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Inject project context:**
   ```bash
   python3 "$HELIX/lib/context.py" build-planner-context --objective "$OBJECTIVE"
   ```

2. **Spawn planner** (opus, foreground, returns PLAN_SPEC):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-planner</parameter>
     <parameter name="prompt">PROJECT_CONTEXT: {context}
   OBJECTIVE: {objective}
   EXPLORATION: {findings}</parameter>
     <parameter name="max_turns">12</parameter>
     <parameter name="description">Plan task DAG</parameter>
   </invoke>
   ```

   Planner runs in foreground and returns a `PLAN_SPEC:` JSON block describing the task DAG.

3. **Create tasks from PLAN_SPEC:** Parse the JSON array from planner output. For each task spec:
   ```xml
   <invoke name="TaskCreate">
     <parameter name="subject">{spec.seq}: {spec.slug}</parameter>
     <parameter name="description">{spec.description}</parameter>
     <parameter name="activeForm">Building {spec.slug}</parameter>
     <parameter name="metadata">{"seq": "{spec.seq}", "relevant_files": {spec.relevant_files}}</parameter>
   </invoke>
   ```
   Track: `seq_to_id[spec.seq] = task_id` from result.

4. **Set dependencies:** After all tasks created, for each spec with blocked_by:
   ```xml
   <invoke name="TaskUpdate">
     <parameter name="taskId">{seq_to_id[spec.seq]}</parameter>
     <parameter name="addBlockedBy">["{seq_to_id[b]}", ...]</parameter>
   </invoke>
   ```

5. **Extract decisions:** Call TaskList, then construct JSON array from results:
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
    7. Learn from outcome (see below)
```

**For each completed task:**

1. Get task details via TaskGet, then construct JSON and build context:
   ```xml
   <invoke name="TaskGet">
     <parameter name="taskId">{task_id}</parameter>
   </invoke>
   ```

   From the result, construct task JSON and call:
   ```bash
   python3 "$HELIX/lib/context.py" build-context --task-data '{"id": "1", "subject": "001: task-slug", "description": "...", "metadata": {"relevant_files": [...]}}'
   ```

   Note: TaskGet returns human-readable text, not JSON. The orchestrator must parse the result and construct the JSON object manually.

2. Spawn builder:
```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-builder</parameter>
  <parameter name="prompt">{context}</parameter>
  <parameter name="max_turns">15</parameter>
  <parameter name="run_in_background">true</parameter>
  <parameter name="description">Build task {id}</parameter>
</invoke>
```

**On DELIVERED:** `git stash drop` — changes are good.
**On BLOCKED:** `git stash pop` — revert, reassess.

### LEARN

This is where you invest in your future self. After each task completes:

**1. Credit what helped:**
```bash
python3 "$HELIX/lib/memory/core.py" feedback --names '[injected_memories]' --delta 0.5
```
See `reference/feedback-deltas.md` for delta calibration.

**2. Store discoveries:**
- Delivered with non-obvious insight → store as `pattern`
- Blocked with generalizable cause → store as `failure`
- Trivial success → skip (noise)

```bash
python3 "$HELIX/lib/memory/core.py" store --type pattern --trigger "SPECIFIC" --resolution "ACTIONABLE"
```

**3. Connect knowledge:**
```bash
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
# Review suggestions, create edges that make sense:
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves
```

**4. Detect systemic issues:**
```bash
python3 "$HELIX/lib/memory/core.py" similar-recent "failure trigger" --threshold 0.7 --days 7
```
If 2+ similar failures → escalate to `systemic` type.

**5. Extract evolution:** Construct task JSON from TaskGet result:
```bash
python3 "$HELIX/lib/observer.py" builder --task '{"id": "1", "subject": "...", "metadata": {...}}' --files-changed "$(git diff --name-only HEAD~1)" --store
```
Note: Orchestrator constructs JSON from TaskGet text output.

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

Contracts in `agents/*.md`.

---

## Agent Lifecycle & Wait Primitives

The `output_file` from Task (with `run_in_background=true`) **is** the wait primitive:
- Exists immediately when agent spawns
- Grows as agent works (JSONL)
- Contains completion markers
- Can be watched with grep (~0 context cost)

### Pattern: SPAWN → WATCH → RETRIEVE

```
1. SPAWN:    Task with run_in_background=true → returns output_file
2. WATCH:    grep output_file for completion markers (zero context)
3. RETRIEVE: TaskGet for metadata, TaskList for DAG state
```

### Completion Markers by Agent Type

| Agent | Completion Markers | Where to Find Result |
|-------|-------------------|---------------------|
| builder | `DELIVERED:`, `BLOCKED:` | TaskGet → metadata.helix_outcome |
| explorer | `"status":` | Last JSON block in output_file |
| planner | `PLAN_COMPLETE:`, `ERROR:` | PLAN_SPEC JSON in returned result |

### Wait Utility

```bash
# Instant check (no waiting)
python3 "$HELIX/lib/wait.py" check --output-file "$FILE" --agent-type builder

# Wait with timeout
python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder --timeout 300

# Extract structured content from completed output
python3 "$HELIX/lib/wait.py" extract --output-file "$FILE" --agent-type explorer

# Get last JSON block (explorer findings)
python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"
```

### Why Not TaskOutput?

`TaskOutput` with `block=true` loads the full JSONL transcript—every tool call, every intermediate turn, potentially 70KB+ of execution trace. You pay this context cost just to check "is it done?"

The wait primitive costs ~0 context: grep scans the file without loading it into your conversation.

**Rule: Never use TaskOutput.** Exception: Debugging failed agents when full trace needed.

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
# Recall with graph expansion
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Store a pattern
python3 "$HELIX/lib/memory/core.py" store --type pattern --trigger "..." --resolution "..."

# Credit memories
python3 "$HELIX/lib/memory/core.py" feedback --names '[...]' --delta 0.5

# Check system health
python3 "$HELIX/lib/memory/core.py" health

# Find systemic patterns
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7
```

Full CLI: `reference/cli-reference.md`

---

## The Deal

Every session is a transaction. You receive what past sessions learned. You pay back what this session discovers.

The memories that help get stronger. The memories that mislead get weaker. The graph grows connections. The system learns.

But only if you close the loop.

Your future self is counting on you.
