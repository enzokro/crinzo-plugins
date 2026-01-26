---
name: helix
description: Self-learning orchestrator with semantic memory graph. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

When: Multi-step implementation requiring exploration.
Not when: Simple edits, questions, single-file changes.

**Core Principle:** 9 core primitives + 2 code-assisted, my judgment, graph connects knowledge.

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

### Discover structure

```bash
git ls-files | head -80
```

Identify 3-6 natural partitions:

| Codebase Signal | Partition Strategy |
|-----------------|-------------------|
| Clear directory structure | One partition per top-level directory |
| Microservices/modules | One partition per service/module |
| Frontend/backend split | Separate partitions for each |
| Framework-organized | Follow framework conventions |

**Always include**: A `memory` scope for relevant failures/patterns.

### Spawn explorer swarm

```python
# Launch in parallel (single message, multiple Task calls)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/api/\nFOCUS: route handlers\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
Task(subagent_type="helix:helix-explorer", prompt="SCOPE: memory\nFOCUS: failures and patterns\nOBJECTIVE: {objective}", model="haiku", run_in_background=True)
```

### Collect and merge

Synthesize explorer JSON: dedupe files, resolve conflicts, aggregate findings.
If `targets.files` empty: **EMPTY_EXPLORATION** - broaden scope or clarify.

---

## 2. PLAN

**Input:** Objective + merged exploration.
**Output:** Task DAG via native TaskCreate.

See `reference/task-granularity.md` for sizing heuristics.

### Spawn planner

```python
Task(subagent_type="helix:helix-planner", prompt=f"OBJECTIVE: {objective}\n\nEXPLORATION:\n{json.dumps(merged_exploration, indent=2)}")
```

Planner outputs task mapping + validates DAG (no cycles).

### Validate

- No tasks: **NO_TASKS** - add exploration context.
- Clarify needed: Present questions via AskUserQuestion, re-plan.

---

## 3. BUILD

**Input:** Task DAG from planner.
**Output:** All tasks completed (delivered or blocked).

### Build Loop

```
1. TaskList() -> filter status="pending" -> if empty: goto CLOSE_LOOP
2. Get ready tasks (all blockers have helix_outcome="delivered")
3. If no ready but pending exist: STALLED (see reference/stalled-recovery.md)
4. Spawn ALL ready tasks in parallel (run_in_background=True)
5. Collect results via TaskOutput
6. Process each: verify -> feedback -> learn (steps D-H below are MANDATORY)
7. Go to 1
```

### Close Learning Loop (MANDATORY after all tasks complete)

Before transitioning to COMPLETE, I MUST:

**1. Credit memories that helped** (if any were injected):
```bash
python3 "$HELIX/lib/memory/core.py" feedback --names '[INJECTED_MEMORY_NAMES]' --delta 0.5
```

**2. Decide on pattern storage** for each delivered task:
```
For each task with helix_outcome="delivered":
  Q: Did this require non-obvious discovery that would help future tasks?
  If YES -> store pattern:
    python3 "$HELIX/lib/memory/core.py" store --type pattern \
      --trigger "SPECIFIC_TRIGGER" --resolution "SPECIFIC_RESOLUTION" \
      --source "{task.subject}"
  If NO -> skip (trivial success)
```

**3. Decide on failure storage** for each blocked task:
```
For each task with helix_outcome="blocked":
  Q: Is the cause generalizable (not one-off)?
  If YES -> store failure:
    python3 "$HELIX/lib/memory/core.py" store --type failure \
      --trigger "SPECIFIC_TRIGGER" --resolution "HOW_TO_AVOID" \
      --source "{task.subject}"
```

**4. Check memory health**:
```bash
python3 "$HELIX/lib/memory/core.py" health
```
If `with_feedback: 0` and memories were injected, the loop was not closed properly.

### Execute Single Task

**A. Build context**
```bash
memories=$(python3 "$HELIX/lib/memory/core.py" recall "$OBJECTIVE" --limit 5 --expand)
context=$(python3 "$HELIX/lib/context.py" build-context --task-data "$(TaskGet {task_id} | jq -c)" --lineage "$lineage")
```

**B. Spawn builder**
```python
Task(subagent_type="helix:helix-builder", prompt=prompt, run_in_background=True)
```

**C. Parse result**
```bash
python3 "$HELIX/lib/tasks.py" parse-output "{builder_output}"
```

**D. Run verification**
```bash
timeout 120 {task.metadata.verify}
```

**E. Feedback loop** (see `reference/feedback-deltas.md`)
```bash
python3 "$HELIX/lib/memory/core.py" feedback --names '["memory-name"]' --delta 0.5
```

**F. Edge creation** (see `reference/edge-creation.md`)
```bash
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves
```

**G. Systemic detection**
```bash
python3 "$HELIX/lib/memory/core.py" similar-recent "failure trigger" --threshold 0.7 --days 7 --type failure
```
If 2+ similar: escalate to systemic type.

**H. Learning extraction**

| Condition | Action |
|-----------|--------|
| Trivial success, no insight | Skip |
| Success required non-obvious discovery | Store pattern |
| Blocked with generalizable cause | Store failure |

Quality gates: Would it change future outcomes? Trigger specific? Resolution actionable?

---

## 4. COMPLETE

All tasks done AND learning loop closed. Session ends.

**Pre-completion checklist:**
- [ ] All tasks have `helix_outcome` set (delivered/blocked/skipped)
- [ ] Injected memories received feedback (if any)
- [ ] Pattern/failure storage decisions made for each task
- [ ] `health` shows `with_feedback > 0` if memories were used

---

## Error Recovery

| Error | Detection | Recovery |
|-------|-----------|----------|
| EMPTY_EXPLORATION | `targets.files` empty | Broaden scope, clarify |
| NO_TASKS | Planner created 0 tasks | Add exploration context |
| CYCLES_DETECTED | Planner validates DAG | Planner restructures internally |
| STALLED | Pending but none ready | See `reference/stalled-recovery.md` |
| SYSTEMIC_FAILURE | Same pattern 3+ times | Store systemic, inject as warning |

---

## Agent Contracts

| Agent | Model | Purpose |
|-------|-------|---------|
| helix-explorer | haiku | Parallel reconnaissance, scoped |
| helix-planner | opus | Task decomposition, DAG creation |
| helix-builder | opus | Single task execution |

Contracts define I/O schemas in `agents/*.md`.

---

## Task Status Model

**Dual status**: Native `status` (DAG execution) + `helix_outcome` (semantic result).

| status | helix_outcome | Meaning |
|--------|---------------|---------|
| completed | delivered | Success, memory credit |
| completed | blocked | Finished but didn't achieve goal |
| completed | skipped | Intentionally bypassed (stall recovery) |
| pending | - | Not yet started |
| in_progress | - | Builder executing |

`status=completed` releases dependents. `helix_outcome` determines success context.

---

## Lineage Format

```json
[{"seq": "001", "slug": "setup-auth", "delivered": "Created AuthService with JWT support"}]
```

---

## CLI Quick Reference

See `reference/cli-reference.md` for full commands.

**Essential:**
```bash
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."
python3 "$HELIX/lib/memory/core.py" feedback --names '[...]' --delta 0.5
python3 "$HELIX/lib/memory/core.py" health
```

---

## The Philosophy

Code surfaces facts; I decide actions.

**9 core primitives** for storage, retrieval, and maintenance.
**2 code-assisted functions** that surface facts:
- `similar-recent` -> surfaces similar memories; I decide escalation
- `suggest-edges` -> surfaces candidate edges; I decide which to create

The graph connects knowledge. Code amplifies judgment.
