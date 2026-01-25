---
name: helix
description: Self-learning orchestrator with semantic memory graph. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

When: Multi-step implementation requiring exploration.
Not when: Simple edits, questions, single-file changes.

**Core Principle:** 9 primitives, my judgment, graph connects knowledge.

## Environment

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
```

## States

```
INIT -> EXPLORING -> EXPLORED -> PLANNING -> PLANNED -> BUILDING -> DONE
                                                  |
                                               STALLED -> (replan | skip | abort)
```

State is implicit in conversation flow.

---

## 1. EXPLORE

**Input:** User objective.
**Output:** Merged exploration with non-empty `targets.files`.

### Step 1: Discover structure

```bash
git ls-files | head -80
```

**Judgment:** Identify 3-6 natural partitions. Directories, modules, layers. Always include `memory` scope.

### Step 2: Spawn explorer swarm

```python
# Launch in parallel for each identified partition (single message, multiple Task calls)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/api/\nFOCUS: route handlers\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/models/\nFOCUS: data schemas\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: memory\nFOCUS: failures and patterns\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
```

### Step 3: Collect and merge

```python
TaskOutput(task_id=explorer1_id)
TaskOutput(task_id=explorer2_id)
# ... for each explorer
```

**Judgment:** Synthesize explorer JSON outputs:
- Dedupe file lists
- Resolve conflicting framework detection (prefer HIGH confidence)
- Aggregate findings, patterns, memories
- `targets.files` = union of relevant files found

### Step 4: Validate

If `targets.files` empty: **EMPTY_EXPLORATION**.
- Broaden scope patterns, different focus terms, or clarify with user.

---

## 2. PLAN

**Input:** Objective + merged exploration.
**Output:** Task DAG via native TaskCreate.

### Step 1: Spawn planner

```python
Task(
    subagent_type="helix:helix-planner",
    prompt=f"OBJECTIVE: {objective}\n\nEXPLORATION:\n{json.dumps(merged_exploration, indent=2)}"
)
```

### Step 2: Capture task mapping

Planner outputs:
```
TASK_MAPPING:
001 -> task-abc123
002 -> task-def456

PLAN_COMPLETE: 2 tasks
```

Parse this to track seq-to-taskId mapping.

### Step 3: Validate

- No tasks created: **NO_TASKS**. Re-plan with more exploration context.
- Planner outputs `{"decision": "CLARIFY", "questions": [...]}`: Present questions via AskUserQuestion, then re-plan.

---

## 3. BUILD

**Input:** Task DAG from planner.
**Output:** All tasks completed (delivered or blocked).

### Build Loop

```
1. TaskList() → filter status="pending" → if empty: DONE
2. Get ready tasks (all blockers have helix_outcome="delivered")
3. If no ready tasks but pending exist: STALLED
4. Spawn ALL ready tasks in parallel (run_in_background=True)
5. Collect results via TaskOutput
6. Process each result: verify, feedback, learn
7. Go to 1
```

### Parallel Execution (Natural)

When multiple tasks are ready, spawn them all in a single message:

```python
# Multiple ready tasks - spawn all at once
Task(subagent_type="helix:helix-builder", prompt=context_001, run_in_background=True)  # → id-A
Task(subagent_type="helix:helix-builder", prompt=context_002, run_in_background=True)  # → id-B
Task(subagent_type="helix:helix-builder", prompt=context_003, run_in_background=True)  # → id-C

# Then collect all
TaskOutput(task_id=id-A)
TaskOutput(task_id=id-B)
TaskOutput(task_id=id-C)
```

### Execute Single Task

**Step A: Build context**

```bash
# Recall memories with graph expansion
memories=$(python3 "$HELIX/lib/memory/core.py" recall "$OBJECTIVE" --limit 5 --expand)

# Build context
context=$(python3 "$HELIX/lib/context.py" build-context \
    --task-data "$(TaskGet {task_id} | jq -c)" \
    --lineage "$lineage")

prompt=$(echo "$context" | jq -r '.prompt')
injected=$(echo "$context" | jq -c '.injected')
```

**Step B: Spawn builder**

```python
Task(subagent_type="helix:helix-builder", prompt=prompt, run_in_background=True)
```

**Step C: Parse result**

```bash
python3 "$HELIX/lib/tasks.py" parse-output "{builder_output}"
```

Returns `{"status": "delivered"|"blocked", "summary": "...", ...}`.

**Step D: Run verification**

```bash
# Always use timeout to prevent hangs
timeout 120 {task.metadata.verify}

# If command not found, validate first
which {cmd} || echo "Command not found: {cmd}"
```

Capture exit code. `0` = passed.

**Step E: Close feedback loop (my judgment)**

I decide the delta based on context:

| Situation | Delta | Rationale |
|-----------|-------|-----------|
| Clear success, memory was relevant | +0.7 | Strong signal |
| Success, memory was tangential | +0.3 | Weak signal |
| Success, no memories used | 0 | No feedback |
| Failure, memory may have misled | -0.5 | Moderate penalty |
| Failure, memory was irrelevant | -0.2 | Light penalty |

```bash
python3 "$HELIX/lib/memory/core.py" feedback \
    --names '["memory-name-1", "memory-name-2"]' \
    --delta 0.5
```

**Step F: Edge creation (when pattern solves failure)**

When a pattern helped avoid a previously-encountered failure:

```bash
python3 "$HELIX/lib/memory/core.py" edge \
    --from "pattern-that-helped" \
    --to "failure-it-solved" \
    --rel solves
```

This connects knowledge. Next recall with `--expand` will surface solutions via edges.

**Step G: Systemic detection (3x same failure)**

When the same failure pattern occurs 3+ times in a session:

```bash
python3 "$HELIX/lib/memory/core.py" store \
    --type systemic \
    --trigger "Repeated: {pattern_description}" \
    --resolution "UNRESOLVED"
```

Mark as systemic. Recall will surface these as warnings.

**Step H: Learning extraction (judgment)**

| Condition | Action |
|-----------|--------|
| Trivial success, no insight | Skip |
| Success required non-obvious discovery | Store pattern |
| Blocked with generalizable cause | Store failure |
| Blocked with one-off issue | Skip |

Quality gates:
1. Would this memory change future outcomes? (counterfactual)
2. Is trigger specific enough to match right situations?
3. Is resolution actionable without additional context?

```bash
python3 "$HELIX/lib/memory/core.py" store \
    --type {failure|pattern} \
    --trigger "Precise condition" \
    --resolution "Specific action" \
    --source "{task.subject}"
```

---

## 4. COMPLETE

All tasks done. Session ends.

---

## Error Recovery

| Error | Detection | Recovery |
|-------|-----------|----------|
| EMPTY_EXPLORATION | `targets.files` empty | Broaden scope, clarify with user |
| NO_TASKS | Planner created 0 tasks | Add exploration context |
| CYCLES_DETECTED | Dependency graph has cycles | Re-plan |
| STALLED | Pending tasks, none ready | Replan / Skip blocked / Abort |
| SYSTEMIC_FAILURE | Same pattern 3+ times | Store systemic memory, inject as warning |

---

## CLI Reference

### Memory (9 Primitives)

```bash
# Store
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."

# Recall (with graph expansion)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Get single memory
python3 "$HELIX/lib/memory/core.py" get "memory-name"

# Create edge
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves

# Query edges
python3 "$HELIX/lib/memory/core.py" edges --name "memory-name"

# Feedback (I decide delta)
python3 "$HELIX/lib/memory/core.py" feedback --names '["mem1", "mem2"]' --delta 0.5

# Decay dormant memories
python3 "$HELIX/lib/memory/core.py" decay --days 30 --min-uses 2

# Prune ineffective memories
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Health check
python3 "$HELIX/lib/memory/core.py" health
```

### Tasks

```bash
python3 "$HELIX/lib/tasks.py" parse-output "$output"
python3 "$HELIX/lib/tasks.py" feedback-verify --task-id "..." --verify-passed true --injected '[...]'
```

### Context

```bash
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[...]'
python3 "$HELIX/lib/context.py" build-context --task-data '{...}' --lineage '[...]'
```

### Orchestrator Utilities

```bash
python3 "$HELIX/lib/orchestrator.py" clear
python3 "$HELIX/lib/orchestrator.py" detect-cycles --dependencies '{...}'
python3 "$HELIX/lib/orchestrator.py" check-stalled --tasks '[...]'
```

---

## Lineage Format

Parent deliveries passed to builders:

```json
[
  {"seq": "001", "slug": "setup-auth", "delivered": "Created AuthService with JWT support"},
  {"seq": "002", "slug": "add-routes", "delivered": "Added /login and /logout endpoints"}
]
```

Builders use this context to understand what blockers produced.

---

## Agent Contracts

| Agent | Model | Purpose |
|-------|-------|---------|
| helix-explorer | haiku | Parallel reconnaissance, scoped |
| helix-planner | opus | Task decomposition, DAG creation |
| helix-builder | opus | Single task execution |

Contracts define input/output schemas in `agents/*.md`.

---

## The Philosophy

The code is muscle. I am mind.

9 primitives. My judgment drives everything:
- What weight to pass to `feedback()`
- When to create edges and what type
- When to store systemic patterns
- What memories to inject

Graph connects knowledge. Parallel is natural. Systemic patterns are just memories.
