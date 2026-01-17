---
name: ftl
description: Task execution with learning
version: 2.6.0
---

# FTL Protocol

## Entry Points

| Command | Flow |
|---------|------|
| `/ftl <task>` | EXPLORE → PLAN → BUILD → OBSERVE |
| `/ftl campaign "obj"` | EXPLORE → PLAN → [BUILD]* → OBSERVE |
| `/ftl query "topic"` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py query "topic"` |
| `/ftl status` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py status` |
| `/ftl stats` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py stats` |
| `/ftl prune` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py prune` |
| `/ftl related "name"` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py related "name"` |
| `/ftl similar` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py find-similar` |
| `/ftl observe` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py analyze` |
| `/ftl benchmark` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py report` |

## Agents

| Agent | Role | Model | Budget |
|-------|------|-------|--------|
| **Explorer** | Parallel codebase exploration | haiku | 4 |
| **Planner** | Decompose into verifiable tasks | opus | unlimited |
| **Builder** | Transform spec into code | opus | 3-7 |
| **Observer** | Extract patterns from work | opus | 10 |

## Paths

All CLI commands use `${CLAUDE_PLUGIN_ROOT}` for the plugin installation directory.
See [CLI_REFERENCE.md](CLI_REFERENCE.md) for complete syntax.

---

## TASK State Machine

```
STATE: INIT
  EMIT: STATE_ENTRY state=INIT
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear
  EMIT: PHASE_TRANSITION from=init to=explore
  GOTO: EXPLORE

STATE: EXPLORE
  EMIT: STATE_ENTRY state=EXPLORE agents=4
  DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
      - Task(ftl:ftl-explorer) "mode=structure"
      - Task(ftl:ftl-explorer) "mode=pattern, objective={task}"
      - Task(ftl:ftl-explorer) "mode=memory, objective={task}"
      - Task(ftl:ftl-explorer) "mode=delta, objective={task}"
  WAIT: All 4 complete (explorers write to .ftl/cache/explorer_{mode}.json)
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{task}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
  EMIT: PHASE_TRANSITION from=explore to=plan
  GOTO: PLAN

STATE: PLAN
  EMIT: STATE_ENTRY state=PLAN
  DO: Task(ftl:ftl-planner) with task + exploration.json
  IF: Returns CLARIFY → EMIT: DECISION decision=clarify, ASK user, GOTO PLAN
  IF: Returns plan.json → EMIT: PHASE_TRANSITION from=plan to=build, GOTO BUILD

STATE: BUILD
  EMIT: STATE_ENTRY state=BUILD
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan plan.json
  DO: Task(ftl:ftl-builder) with workspace path
  EMIT: PHASE_TRANSITION from=build to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  DO: Task(ftl:ftl-observer)
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE
```

---

## CAMPAIGN State Machine

```
STATE: INIT
  EMIT: STATE_ENTRY state=INIT mode=campaign
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear
  EMIT: PHASE_TRANSITION from=init to=explore
  GOTO: EXPLORE

STATE: EXPLORE
  EMIT: STATE_ENTRY state=EXPLORE agents=4
  DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
      - Task(ftl:ftl-explorer) "mode=structure"
      - Task(ftl:ftl-explorer) "mode=pattern, objective={objective}"
      - Task(ftl:ftl-explorer) "mode=memory, objective={objective}"
      - Task(ftl:ftl-explorer) "mode=delta, objective={objective}"
  WAIT: All 4 complete
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{objective}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
  EMIT: PHASE_TRANSITION from=explore to=plan
  GOTO: PLAN

STATE: PLAN
  EMIT: STATE_ENTRY state=PLAN
  DO: Task(ftl:ftl-planner) with objective + exploration.json
  IF: Returns CLARIFY → EMIT: DECISION decision=clarify, ASK user, GOTO PLAN
  IF: Returns plan.json → EMIT: PHASE_TRANSITION from=plan to=register, GOTO REGISTER

STATE: REGISTER
  EMIT: STATE_ENTRY state=REGISTER
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective"
  DO: cat plan.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks
  EMIT: PHASE_TRANSITION from=register to=execute
  GOTO: EXECUTE

STATE: EXECUTE
  EMIT: STATE_ENTRY state=EXECUTE
  DO: ready = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks
  EMIT: READY_TASKS count={len(ready)}
  IF: ready is empty → EMIT: PHASE_TRANSITION from=execute to=cascade, GOTO CASCADE
  DO: FOR EACH task in ready (launch in PARALLEL):
        echo '{plan.json}' | python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan - --task {SEQ}
        Task(ftl:ftl-builder) with workspace
        python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ complete|blocked
  GOTO: EXECUTE

STATE: CASCADE
  EMIT: STATE_ENTRY state=CASCADE
  DO: cascade = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status
  IF: cascade.state == "stuck" → EMIT: CASCADE_PROPAGATE, DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks
  EMIT: PHASE_TRANSITION from=cascade to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  SKIP_IF: All tasks blocked with same root cause (single failure cascaded)
  DO: Task(ftl:ftl-observer)
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE
```

---

## Workspace Lifecycle

```
.ftl/workspace/NNN_slug_status.xml
```

Status transitions: `active` → `complete` | `blocked`

**Blocking is success** (informed handoff for Observer to learn from).

---

## Constraints

| Tier | Meaning | Action |
|------|---------|--------|
| **Essential** | Critical | Escalate |
| **Quality** | Important | Note |

---

## DAG Parallelization

Tasks with `depends: ["001", "002"]` wait for both 001 AND 002 to complete.
Tasks with no dependencies or all dependencies complete can run in parallel.

### DAG Cycle Detection

The campaign system prevents cycles during task registration:

```
Algorithm: detect_cycles(tasks)
  1. Build adjacency list from task.depends
  2. For each task:
     - DFS from task
     - Track visited + recursion_stack
     - If task in recursion_stack → CYCLE DETECTED
  3. Return: has_cycle, cycle_path

Implementation: campaign.py::add_tasks()
  - Validates DAG before accepting tasks
  - Rejects plan.json if cycle detected
  - Returns error with cycle path for debugging
```

### Ready Task Selection

```
Algorithm: ready_tasks(campaign)
  1. Get all tasks with status = "pending"
  2. For each pending task:
     - Get depends[] list
     - If depends is empty or "none" → ready
     - If ALL depends have status = "complete" → ready
     - Otherwise → not ready
  3. Return ready tasks

Complexity: O(T) where T = number of tasks
```

### Cascade Handling

When a parent task blocks, child tasks become unreachable.

```
Algorithm: cascade_status(campaign)
  1. Get all blocked tasks → blocked_set
  2. For each pending task:
     - If ANY depends in blocked_set → unreachable
  3. Return: {state: "stuck" | "progressing", unreachable: [...]}

Algorithm: propagate_blocks(campaign)
  1. For each unreachable task from cascade_status:
     - Set status = "blocked"
     - Set blocked_by = blocking parent seq
     - Record as cascade (not original failure)
```

**On-Demand Workspace Creation**: Workspaces are created AFTER parent tasks complete.
This enables proper `<lineage>` population with parent deliveries and sibling failure injection.

---

## Sibling Failure Injection

Sibling failures enable intra-campaign learning: failures from one branch inform parallel branches.

### Injection Timing

| Event | What Happens |
|-------|--------------|
| Plan created | Tasks defined with dependencies, no workspaces yet |
| Task 001 starts | Workspace created with memory.get_context() only |
| Task 001 blocks | Failure recorded in 001_slug_blocked.xml |
| Task 002 starts | Workspace created with memory failures + sibling failures from 001 |

### Implementation Flow

```
workspace.create(plan, task_seq):
  1. Get memory context: memory.get_context(objective)
  2. Scan for sibling failures: get_sibling_failures(WORKSPACE_DIR)
     - Glob for *_blocked.xml
     - Extract trigger from delivered text
     - Create synthetic failure entries
  3. Combine: all_failures = memory_failures + sibling_failures
  4. Inject into <prior_knowledge> section

get_sibling_failures(workspace_dir):
  FOR each *_blocked.xml in workspace_dir:
    IF delivered contains "BLOCKED:":
      YIELD {
        name: "sibling-{stem}",
        trigger: first_line_of_reason,
        fix: "See blocked workspace",
        cost: 1000,
        source: [blocked_workspace_id]
      }
```

### Why Not During Planning?

The planner runs once BEFORE any building starts. Sibling failures only exist AFTER
builders encounter them. The dynamic injection at workspace creation time ensures:

1. **Freshness**: Latest failures from concurrent branches
2. **Relevance**: Only failures from same campaign
3. **Context**: Failures include workspace stem for traceability

### Sibling vs Memory Failures

| Attribute | Memory Failures | Sibling Failures |
|-----------|-----------------|------------------|
| Source | Historical memory.json | Current campaign blocked.xml |
| Relevance scoring | Semantic similarity | Always injected |
| injected attribute | "true" | "false" (for feedback tracking) |
| Feedback tracking | Yes (times_helped/failed) | No (ephemeral) |

---

## Handoff Contracts

### plan.json (Planner → Orchestrator)

```json
{
  "_schema_version": "1.0",
  "objective": "string (required)",
  "campaign": "string (required)",
  "framework": "string | null",
  "idioms": {"required": [], "forbidden": []},
  "tasks": [
    {
      "seq": "string (required, 3-digit)",
      "slug": "string (required)",
      "type": "SPEC | BUILD | VERIFY",
      "delta": ["string (required, file paths)"],
      "verify": "string (required)",
      "budget": "number (required)",
      "depends": "string | string[] | 'none'"
    }
  ]
}
```

**Required fields**: objective, tasks[].seq, tasks[].delta, tasks[].verify

### Workspace Creation Contract

| Flow | When Created | Prior Knowledge Source |
|------|--------------|------------------------|
| TASK | Immediately after plan.json | memory.get_context() only |
| CAMPAIGN | On-demand after parent completion | memory.get_context() + sibling failures |

**Lineage Population**: Child workspaces include `<lineage>` with parent deliveries,
enabling contextual understanding of completed work.

---

## References

- [CLI_REFERENCE.md](CLI_REFERENCE.md) - Complete command syntax
- [MEMORY_SEMANTICS.md](MEMORY_SEMANTICS.md) - Memory decay, feedback, and graph traversal
