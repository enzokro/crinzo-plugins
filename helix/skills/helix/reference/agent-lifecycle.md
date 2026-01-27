# Agent Lifecycle

Complete reference for spawning, watching, and retrieving results from helix agents.

## The Problem

`TaskOutput(block=true)` conflates waiting and retrieval, charging 70KB+ transcript for a simple "is it done?" check. Notifications arrive late/async. The orchestrator needs a zero-cost wait primitive.

## The Solution

The `output_file` from `Task(..., run_in_background=True)` **is** the wait primitive:
- Exists immediately when agent spawns
- Grows as agent works (JSONL)
- Contains completion markers
- Can be watched with grep (~0 context cost)

---

## Lifecycle Phases

### 1. SPAWN

Launch agent with `run_in_background=True`. Store the returned `output_file` path.

```python
result = Task(
    subagent_type="helix:helix-builder",
    prompt=context,
    max_turns=15,
    allowed_tools=["Read", "Write", "Edit", "Grep", "Glob", "Bash", "TaskUpdate"],
    run_in_background=True
)
# result contains output_file path
output_file = result.output_file
```

### 2. WATCH

Poll completion using grep-based utilities (~0 context cost).

```bash
# Instant check
python3 "$HELIX/lib/wait.py" check --output-file "$FILE" --agent-type builder

# Wait with timeout
python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder --timeout 300
```

**Do NOT use `TaskOutput`** - it loads the full transcript into your context.

### 3. RETRIEVE

Once completed, retrieve results from the appropriate location:

| Agent | Result Location | How to Retrieve |
|-------|-----------------|-----------------|
| builder | Task metadata | `TaskGet(id)` → `metadata.helix_outcome` |
| explorer | Last JSON in output_file | `python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"` |
| planner | TaskList (DAG) | `TaskList` → inspect created tasks |

---

## Completion Markers

Each agent type emits specific markers when done:

| Agent | Success Marker | Failure Marker |
|-------|----------------|----------------|
| builder | `DELIVERED:` | `BLOCKED:` |
| explorer | `"status": "success"` | `"status": "error"` |
| planner | `PLAN_COMPLETE:` | `ERROR:` |

The wait utility scans for these markers using grep.

---

## Context Cost Comparison

| Approach | Context Cost | When to Use |
|----------|--------------|-------------|
| `grep output_file` | ~0 | Always (check completion) |
| `wait.py check` | ~0 | Always (check completion) |
| `wait.py extract` | ~200 bytes | Get completion content |
| `TaskGet` | ~500 bytes | Get task metadata (builders) |
| `TaskList` | ~1KB | Get DAG state (planners) |
| `TaskOutput` | 10-70KB+ | **NEVER** (except debugging) |

---

## Complete Example

```python
# 1. SPAWN
spawned = []
for task in ready_tasks:
    context = build_context(task)
    result = Task(
        subagent_type="helix:helix-builder",
        prompt=context,
        run_in_background=True,
        allowed_tools=["Read", "Write", "Edit", "Grep", "Glob", "Bash", "TaskUpdate"]
    )
    spawned.append({"task_id": task.id, "output_file": result.output_file})

# 2. WATCH
for agent in spawned:
    Bash(f'python3 "$HELIX/lib/wait.py" wait --output-file "{agent["output_file"]}" --agent-type builder')

# 3. RETRIEVE
for agent in spawned:
    task_data = TaskGet(agent["task_id"])
    outcome = task_data.metadata.get("helix_outcome")
    # Process outcome...
```

---

## Rule

**Never use TaskOutput.** Exception: Debugging failed agents when full trace needed.

- Wait → grep output_file (or wait.py)
- Builder results → TaskGet
- Explorer results → Extract from output_file last block
- Planner results → TaskList
