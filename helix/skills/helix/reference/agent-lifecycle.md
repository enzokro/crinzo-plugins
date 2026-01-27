# Agent Lifecycle

Complete reference for spawning, watching, and retrieving results from helix agents.

## The Problem

`TaskOutput` with `block=true` conflates waiting and retrieval, charging 70KB+ transcript for a simple "is it done?" check. Notifications arrive late/async. The orchestrator needs a zero-cost wait primitive.

## The Solution

The `output_file` from Task (with `run_in_background=true`) **is** the wait primitive:
- Exists immediately when agent spawns
- Grows as agent works (JSONL)
- Contains completion markers
- Can be watched with grep (~0 context cost)

---

## Lifecycle Phases

### 1. SPAWN

Launch agent with `run_in_background=true`. Store the returned `output_file` path.

No `allowed_tools` needed—agents use their frontmatter-defined tools. Project settings pre-approve them.

**Builder example:**
```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-builder</parameter>
  <parameter name="prompt">{context}</parameter>
  <parameter name="max_turns">15</parameter>
  <parameter name="run_in_background">true</parameter>
  <parameter name="description">Build task {id}</parameter>
</invoke>
```

**Explorer example:**
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

**Planner example (foreground—returns PLAN_SPEC):**
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

### 2. WATCH

Poll completion using grep-based utilities (~0 context cost).

```bash
# Instant check
python3 "$HELIX/lib/wait.py" check --output-file "$FILE" --agent-type builder

# Wait with timeout
python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder --timeout 300
```

**Do NOT use `TaskOutput`**—it loads the full transcript into your context.

### 3. RETRIEVE

Once completed, retrieve results from the appropriate location:

| Agent | Result Location | How to Retrieve |
|-------|-----------------|-----------------|
| builder | Task metadata | TaskGet → `metadata.helix_outcome` |
| explorer | Last JSON in output_file | `python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"` |
| planner | PLAN_SPEC in returned result | Parse JSON from planner's text output |

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
| `TaskList` | ~1KB | Get DAG state |
| `TaskOutput` | 10-70KB+ | **NEVER** (except debugging) |

---

## Complete Example

```
# 1. SPAWN builders for ready tasks
for each ready task:
    <invoke name="Task">
      <parameter name="subagent_type">helix:helix-builder</parameter>
      <parameter name="prompt">{context}</parameter>
      <parameter name="max_turns">15</parameter>
      <parameter name="run_in_background">true</parameter>
      <parameter name="description">Build task {id}</parameter>
    </invoke>
    # Store output_file from result

# 2. WATCH for completion
for each spawned agent:
    python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder

# 3. RETRIEVE results
for each completed agent:
    <invoke name="TaskGet">
      <parameter name="taskId">{task_id}</parameter>
    </invoke>
    # Parse helix_outcome from metadata
```

---

## Rule

**Never use TaskOutput.** Exception: Debugging failed agents when full trace needed.

- Wait → grep output_file (or wait.py)
- Builder results → TaskGet
- Explorer results → Extract from output_file last block
- Planner results → PLAN_SPEC JSON in returned result (orchestrator creates tasks)
