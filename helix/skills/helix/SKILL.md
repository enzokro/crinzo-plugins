---
name: helix
description: Task orchestrator with memory. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

When: Multi-step implementation requiring exploration.
Not when: Simple edits, questions, single-file changes.

Orchestration requires judgment. Agents are deterministic.

## Environment

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
```

## States

```
INIT -> EXPLORING -> EXPLORED -> PLANNING -> PLANNED -> BUILDING -> BUILT -> DONE
                                                  |
                                               STALLED -> (replan | skip | abort)
```

State is implicit in conversation flow. Checkpoints persist at EXPLORED, PLANNED, BUILT.

---

## 1. EXPLORE

**Input:** User objective.
**Output:** Merged exploration with non-empty `targets.files`.

### Step 1: Discover structure

```bash
git ls-files | head -80
```

**Judgment:** Identify 3-6 natural partitions. Directories, modules, layers. Always include `memory` and `framework` scopes.

### Step 2: Spawn explorer swarm

```python
# Launch in parallel for each identified partition (single message, multiple Task calls)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/api/\nFOCUS: route handlers\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/models/\nFOCUS: data schemas\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: memory\nFOCUS: failures and patterns\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: framework\nFOCUS: idioms and conventions\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
```

### Step 3: Collect and merge

```python
# Collect each explorer output
TaskOutput(task_id=explorer1_id)
TaskOutput(task_id=explorer2_id)
# ... for each explorer
```

**Judgment:** Synthesize explorer JSON outputs into single exploration:
- Dedupe file lists
- Resolve conflicting framework detection (prefer HIGH confidence)
- Aggregate all findings, patterns, memories
- `targets.files` = union of all relevant files found

### Step 4: Validate

If `targets.files` is empty: **EMPTY_EXPLORATION**.
- **Judgment:** Broaden scope patterns, try different focus terms, or ask user to clarify objective.

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

- If no tasks created: **NO_TASKS**. Re-plan with more exploration context.
- If planner outputs `{"decision": "CLARIFY", "questions": [...]}`: Present questions via AskUserQuestion, then re-plan.

---

## 3. BUILD

**Input:** Task DAG from planner.
**Output:** All tasks completed (delivered or blocked).

### Build Loop

```
1. TaskList() → filter status="pending" → if empty: DONE
2. For each pending: TaskGet(blocker_id) for each in blockedBy
   → ready if all blockers have metadata.helix_outcome="delivered"
3. If no ready tasks: STALLED → AskUserQuestion (Replan | Skip | Abort)
4. For each ready task: execute Steps A–J below
5. Go to 1
```

### Execute Single Task

**Step A: Query memory**

```bash
python3 "$HELIX/lib/memory/core.py" recall "{task.description}" --limit 5
```

Output is JSON list. Extract `name`, `trigger`, `resolution` fields.

**Step B: Check for systemic warnings**

```bash
python3 "$HELIX/lib/memory/meta.py" warnings --objective "{objective}"
```

If `warning` is non-null, include in builder context.

**Step C: Build lineage from completed blockers**

Collect TaskGet output for each delivered blocker, then:

```bash
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[{"subject":"001: auth","metadata":{"helix_outcome":"delivered","delivered_summary":"Added JWT middleware"}}]'
```

Returns `[{"seq": "001", "slug": "auth", "delivered": "Added JWT middleware"}]`.

**Step D: Construct builder prompt**

```
TASK_ID: {task.id}
TASK_SUBJECT: {task.subject}
OBJECTIVE: {task.description}
VERIFY: {task.metadata.verify}
RELEVANT_FILES: {task.metadata.relevant_files}
FRAMEWORK: {task.metadata.framework}
FAILURES_TO_AVOID: ["{trigger} -> {resolution}", ...]
PATTERNS_TO_APPLY: ["{trigger} -> {resolution}", ...]
INJECTED_MEMORIES: ["memory-name-1", "memory-name-2"]
PARENT_DELIVERIES: [{seq, slug, delivered}, ...]
WARNING: {systemic_warning or omit}
```

**Step E: Spawn builder**

```python
Task(subagent_type="helix:helix-builder", prompt=builder_prompt)
```

**Step F: Parse result**

```bash
python3 "$HELIX/lib/tasks.py" parse-output "{builder_output}"
```

Returns `{"status": "delivered"|"blocked", "summary": "...", ...}`.

**Step G: Run verification**

```bash
{task.metadata.verify}
```

Capture exit code. `0` = passed.

**Step H: Close feedback loop**

```bash
python3 "$HELIX/lib/tasks.py" feedback-verify \
    --task-id "{task.id}" \
    --verify-passed {true|false} \
    --injected '["memory-name-1", "memory-name-2"]'
```

**Step I: Record metacognition**

```bash
python3 "$HELIX/lib/memory/meta.py" complete \
    --objective "{objective}" \
    --task-id "{task.id}" \
    --status {delivered|blocked} \
    --duration-ms {elapsed}
```

**Step J: Learning extraction (judgment)**

After task completes, decide whether to store a memory:

| Condition | Action |
|-----------|--------|
| Trivial success, no insight required | Skip |
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

Typical extraction: 0 memories per simple task, 1-2 per challenging or insight task, 1-3 per blocked task.

---

## 4. COMPLETE

All tasks done. Session ends.

---

## Error Recovery

| Error | Detection | Recovery Options |
|-------|-----------|------------------|
| EMPTY_EXPLORATION | `targets.files` empty | Broaden scope, different focus, clarify with user |
| NO_TASKS | Planner created 0 tasks | Add exploration context, clarify requirements |
| CYCLES_DETECTED | Dependency graph has cycles | Planner error; re-plan |
| STALLED | Pending tasks, none ready | Replan / Skip blocked / Abort |
| SYSTEMIC_FAILURE | Same pattern 3+ times | Replan with failure context as WARNING |

---

## CLI Reference

### Memory

```bash
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."
python3 "$HELIX/lib/memory/core.py" health
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.3
```

### Tasks

```bash
python3 "$HELIX/lib/tasks.py" parse-output "$output"
python3 "$HELIX/lib/tasks.py" feedback-verify --task-id "..." --verify-passed true --injected '[...]'
```

### Metacognition

```bash
python3 "$HELIX/lib/memory/meta.py" warnings --objective "..."
python3 "$HELIX/lib/memory/meta.py" complete --objective "..." --task-id "..." --status delivered --duration-ms 5000
python3 "$HELIX/lib/memory/meta.py" health --objective "..."
```

### Context

```bash
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[...]'
python3 "$HELIX/lib/context.py" build-context --task-data '{...}' --lineage '[...]'
```

### Orchestrator

```bash
python3 "$HELIX/lib/orchestrator.py" status --objective "..."
python3 "$HELIX/lib/orchestrator.py" clear
```

---

## Checkpoints

Saved automatically at state boundaries:
- `.helix/checkpoints/explored.json`
- `.helix/checkpoints/planned.json`
- `.helix/checkpoints/built.json`

---

## Agent Contracts

| Agent | Model | Purpose |
|-------|-------|---------|
| helix-explorer | haiku | Parallel reconnaissance, scoped |
| helix-planner | opus | Task decomposition, DAG creation |
| helix-builder | opus | Single task execution |

Contracts define input/output schemas in `agents/*.md`.
