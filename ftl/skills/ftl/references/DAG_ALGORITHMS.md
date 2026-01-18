# DAG Algorithms

Task dependency graph algorithms used by the campaign system.

---

## Overview

Campaigns organize tasks as a Directed Acyclic Graph (DAG):
- **Nodes**: Tasks with sequence numbers (001, 002, ...)
- **Edges**: Dependencies (`depends: ["001", "002"]`)
- **Constraint**: No cycles allowed

```
001 (spec-auth) ──→ 003 (impl-auth) ──┐
                                      ├──→ 005 (integrate)
002 (spec-api) ──→ 004 (impl-api) ───┘
```

Tasks 001 and 002 run in parallel (no dependencies).
Task 005 waits for both 003 AND 004.

---

## Cycle Detection

Prevents invalid task graphs at registration time.

### Algorithm

```
detect_cycles(tasks):
  1. Build adjacency list from task.depends
     - For each task: adj[task.seq] = task.depends

  2. For each task in tasks:
     - visited = set()
     - recursion_stack = set()
     - if dfs(task.seq, visited, recursion_stack):
         return (True, cycle_path)

  3. Return (False, None)

dfs(node, visited, recursion_stack):
  visited.add(node)
  recursion_stack.add(node)

  for neighbor in adj[node]:
    if neighbor not in visited:
      if dfs(neighbor, visited, recursion_stack):
        return True
    elif neighbor in recursion_stack:
      # Cycle found
      return True

  recursion_stack.remove(node)
  return False
```

### Implementation

Located in `campaign.py::add_tasks()`:

```python
def add_tasks(tasks):
    # Validate DAG before accepting
    has_cycle, cycle_path = detect_cycles(tasks)
    if has_cycle:
        raise ValueError(f"Cycle detected: {' → '.join(cycle_path)}")

    # Safe to register tasks
    for task in tasks:
        register_task(task)
```

### Error Handling

When cycle detected:
- Registration rejected
- Error message includes cycle path
- Example: `"Cycle detected: 001 → 003 → 005 → 001"`

---

## Ready Task Selection

Determines which tasks can execute in current iteration.

### Algorithm

```
ready_tasks(campaign):
  1. Get all tasks with task_state = "pending"

  2. For each pending task:
     depends = task.depends

     if depends is empty or depends == "none":
       → task is ready

     elif ALL tasks in depends have task_state == "complete":
       → task is ready

     else:
       → task is not ready (waiting on dependencies)

  3. Return list of ready tasks

Complexity: O(T × D) where T = tasks, D = max dependencies
           Typically O(T) since D is small
```

### Implementation

Located in `campaign.py::ready_tasks()`:

```python
def ready_tasks():
    campaign = load_campaign()
    ready = []

    for task in campaign["tasks"]:
        if task["task_state"] != "pending":
            continue

        depends = task.get("depends", "none")
        if depends == "none" or not depends:
            ready.append(task)
            continue

        # Normalize to list
        if isinstance(depends, str):
            depends = [depends]

        # Check all dependencies complete
        all_complete = all(
            get_task_state(dep) == "complete"
            for dep in depends
        )

        if all_complete:
            ready.append(task)

    return ready
```

### Execution Pattern

From CAMPAIGN.EXECUTE state:

```
DO: ready_tasks = python3 lib/campaign.py ready-tasks
IF: ready_tasks is empty → GOTO CASCADE
DO: FOR EACH task in ready_tasks (launch in PARALLEL):
      # Create workspace and execute
```

---

## Cascade Status

Detects when campaign is stuck due to blocked parent tasks.

### Algorithm

```
cascade_status(campaign):
  1. Get all blocked tasks → blocked_set
     blocked_set = {task.seq for task in tasks if task.task_state == "blocked"}

  2. Find unreachable tasks:
     unreachable = []
     for task in tasks:
       if task.task_state != "pending":
         continue

       depends = normalize_to_list(task.depends)
       if any(dep in blocked_set for dep in depends):
         unreachable.append(task)

  3. Determine state:
     if unreachable:
       state = "stuck"
     else:
       state = "progressing"

  4. Return {state, unreachable, blocked_set}
```

### Implementation

Located in `campaign.py::cascade_status()`:

```python
def cascade_status():
    campaign = load_campaign()

    blocked_seqs = {
        t["seq"] for t in campaign["tasks"]
        if t["task_state"] == "blocked"
    }

    unreachable = []
    for task in campaign["tasks"]:
        if task["task_state"] != "pending":
            continue

        depends = task.get("depends", [])
        if isinstance(depends, str):
            depends = [depends] if depends != "none" else []

        if any(dep in blocked_seqs for dep in depends):
            unreachable.append(task["seq"])

    return {
        "state": "stuck" if unreachable else "progressing",
        "unreachable": unreachable,
        "blocked": list(blocked_seqs)
    }
```

---

## Block Propagation

Marks unreachable tasks as blocked to prevent infinite waiting.

### Algorithm

```
propagate_blocks(campaign):
  1. Get cascade_status

  2. For each unreachable task:
     - Set task_state = "blocked"
     - Set blocked_by = first blocking parent
     - Set cascade = True (not original failure)

  3. Save campaign state
```

### Implementation

Located in `campaign.py::propagate_blocks()`:

```python
def propagate_blocks():
    status = cascade_status()
    campaign = load_campaign()

    blocked_seqs = set(status["blocked"])

    for task in campaign["tasks"]:
        if task["seq"] not in status["unreachable"]:
            continue

        # Find which dependency caused the block
        depends = normalize_depends(task.get("depends", []))
        blocking_parent = next(
            (dep for dep in depends if dep in blocked_seqs),
            None
        )

        task["task_state"] = "blocked"
        task["blocked_by"] = blocking_parent
        task["cascade"] = True

    save_campaign(campaign)
```

### Cascade vs Original Failure

| Attribute | Original Failure | Cascade Block |
|-----------|------------------|---------------|
| `task_state` | "blocked" | "blocked" |
| `blocked_by` | None | Parent seq |
| `cascade` | False | True |
| Observer analysis | Full extraction | Skip (no new info) |

---

## Adaptive Re-Planning

When cascade affects significant tasks, attempts to find alternative path.

### Trigger Condition

```
IF: cascade.state == "stuck" AND len(cascade.unreachable) >= 2
```

### Flow

```
1. Get replan input:
   DO: replan_input = python3 lib/campaign.py get-replan-input
   # Returns: {completed_tasks, blocked_tasks, remaining_tasks, objective}

2. Invoke planner with context:
   DO: Task(ftl:ftl-planner) with replan_input > revised_plan.json

3. Merge if valid:
   IF: revised_plan valid →
       DO: python3 lib/campaign.py merge-revised-plan revised_plan.json
       GOTO: EXECUTE
```

### Merge Semantics

`merge-revised-plan` preserves completed work:

1. Keep all tasks with `task_state == "complete"`
2. Replace blocked tasks with revised alternatives
3. Update dependencies to reflect new structure
4. Resume execution with revised DAG

---

## Complexity Summary

| Algorithm | Time | Space | Notes |
|-----------|------|-------|-------|
| `detect_cycles` | O(V + E) | O(V) | Standard DFS |
| `ready_tasks` | O(T × D) | O(T) | D typically small |
| `cascade_status` | O(T × D) | O(T) | Single pass |
| `propagate_blocks` | O(T) | O(1) | Updates in place |

Where:
- V = vertices (tasks)
- E = edges (dependencies)
- T = total tasks
- D = max dependencies per task
