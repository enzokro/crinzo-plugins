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
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear
  GOTO: EXPLORE

STATE: EXPLORE
  DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
      - Task(ftl:ftl-explorer) "mode=structure"
      - Task(ftl:ftl-explorer) "mode=pattern, objective={task}"
      - Task(ftl:ftl-explorer) "mode=memory, objective={task}"
      - Task(ftl:ftl-explorer) "mode=delta, objective={task}"
  WAIT: All 4 complete (explorers write to .ftl/cache/explorer_{mode}.json)
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{task}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
  GOTO: PLAN

STATE: PLAN
  DO: Task(ftl:ftl-planner) with task + exploration.json
  IF: Returns CLARIFY → ASK user, GOTO PLAN
  IF: Returns plan.json → GOTO BUILD

STATE: BUILD
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan plan.json
  DO: Task(ftl:ftl-builder) with workspace path
  GOTO: OBSERVE

STATE: OBSERVE
  DO: Task(ftl:ftl-observer)
  GOTO: COMPLETE
```

---

## CAMPAIGN State Machine

```
STATE: INIT
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear
  GOTO: EXPLORE

STATE: EXPLORE
  DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
      - Task(ftl:ftl-explorer) "mode=structure"
      - Task(ftl:ftl-explorer) "mode=pattern, objective={objective}"
      - Task(ftl:ftl-explorer) "mode=memory, objective={objective}"
      - Task(ftl:ftl-explorer) "mode=delta, objective={objective}"
  WAIT: All 4 complete
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{objective}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
  GOTO: PLAN

STATE: PLAN
  DO: Task(ftl:ftl-planner) with objective + exploration.json
  IF: Returns CLARIFY → ASK user, GOTO PLAN
  IF: Returns plan.json → GOTO REGISTER

STATE: REGISTER
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective"
  DO: cat plan.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks
  GOTO: EXECUTE

STATE: EXECUTE
  DO: ready = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks
  IF: ready is empty → GOTO CASCADE
  DO: FOR EACH task in ready (launch in PARALLEL):
        echo '{plan.json}' | python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan - --task {SEQ}
        Task(ftl:ftl-builder) with workspace
        python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ complete|blocked
  GOTO: EXECUTE

STATE: CASCADE
  DO: cascade = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status
  IF: cascade.state == "stuck" → python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks
  GOTO: OBSERVE

STATE: OBSERVE
  SKIP_IF: All tasks blocked with same root cause (single failure cascaded)
  DO: Task(ftl:ftl-observer)
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete
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

**Cascade Handling**: When a parent task blocks, child tasks become unreachable.
The `cascade-status` command detects this, and `propagate-blocks` marks unreachable
tasks as blocked with their blocking parent reference.

**On-Demand Workspace Creation**: Workspaces are created AFTER parent tasks complete.
This enables proper `<lineage>` population with parent deliveries and sibling failure injection.

---

## References

- [CLI_REFERENCE.md](CLI_REFERENCE.md) - Complete command syntax
- [MEMORY_SEMANTICS.md](MEMORY_SEMANTICS.md) - Memory decay, feedback, and graph traversal
