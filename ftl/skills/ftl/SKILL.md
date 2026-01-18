---
name: ftl
description: Task execution with learning
version: 2.4.13
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
See the CLI docs: [references/CLI_REFERENCE.md](references/CLI_REFERENCE.md) for complete syntax.

---

## DSL Action Verbs

| Verb | Semantics | Example |
|------|-----------|---------|
| `DO:` | Execute command, capture stdout | `DO: python3 lib/foo.py cmd` |
| `DO: \|` | Pipe previous DO's stdout to command | `DO: \| python3 lib/foo.py write` |
| `CHECK:` | Execute, parse JSON output, set local variables | `CHECK: ... wait-explorers` → `wait_result` |
| `EMIT:` | Log structured event or status string | `EMIT: STATE_ENTRY state=INIT` |
| `IF:` | Conditional branch (uses CHECK variables) | `IF: wait_result=="quorum_met" →` |
| `GOTO:` | Jump to named state (fresh context) | `GOTO: PLAN` |
| `WAIT:` | Block until condition or timeout | `WAIT: All 4 complete OR timeout=300s` |
| `TRACK:` | Declare persistent variable across state re-entries | `TRACK: clarify_count` |
| `INCREMENT:` | Increment tracked variable | `INCREMENT: clarify_count` |
| `SET:` | Assign value to tracked variable | `SET: prior_ready_count = len(ready_tasks)` |
| `USE:` | Invoke reusable pattern with substitution | `USE: INIT_PATTERN with mode=campaign` |
| `PROCEED` | Fall through to next instruction | `IF: ... → PROCEED` |
| `PARALLEL` | Execute tasks concurrently in single message | `DO: Task(X) in PARALLEL` |

### Variable Binding

`CHECK:` commands parse JSON stdout and expose fields as local variables:
```
CHECK: python3 lib/orchestration.py wait-explorers
# Exposes: wait_result.status, wait_result.completed, wait_result.missing
IF: wait_result.status=="quorum_met" → ...
```

### State Context

`GOTO:` creates fresh state context. Tracked variables persist; local variables reset.

### Variable Lifecycle

| Type | Initialized | Persists |
|------|-------------|----------|
| Local (from CHECK) | Each state entry | Until GOTO |
| Tracked (from TRACK) | First declaration (default: 0) | Entire session |

TRACK variables initialize on **first encounter**. Subsequent GOTO re-entries preserve values.

### Variable Scope Reference

| Variable | Scope | Used In | Rationale |
|----------|-------|---------|-----------|
| `clarify_count` | TRACK | PLAN_PATTERN | Survives PLAN re-entry; cap at 5 prevents infinite clarification |
| `iteration_count` | TRACK | CAMPAIGN.EXECUTE | Survives EXECUTE re-entry; cap at 20 bounds execution |
| `prior_ready_count` | TRACK | CAMPAIGN.EXECUTE | Detects stuck state (unchanged for 3+ iterations) |
| `wait_result` | Local | EXPLORE_PATTERN | Consumed by IF after CHECK; disposable |
| `decision` | Local | PLAN_PATTERN | Consumed by IF after CHECK; disposable |
| `ready_tasks` | Local | CAMPAIGN.EXECUTE | Fresh each iteration; depends on campaign state |

---

## Defaults & Judgment

These values are **defaults**, not hard limits. Override with stated rationale when context warrants.

| Name | Default | Override When |
|------|---------|---------------|
| `EXPLORER_TIMEOUT` | 300s | Slow network → increase; fast local → decrease |
| `MAX_CLARIFICATIONS` | 5 | Complex ambiguity may need more; trivial needs fewer |
| `MAX_ITERATIONS` | 20 | Large campaigns may need more; simple tasks fewer |
| `STUCK_THRESHOLD` | 3 | Obvious stuck → trigger earlier; subtle progress → allow more |

### Exploration Quorum (Judgment-Based)

Instead of fixed quorum=3, proceed when:
- All 4 explorers complete, OR
- Critical modes complete (structure + delta), OR
- 3+ explorers complete with adequate coverage

State rationale when proceeding with partial results.

### Memory Injection (Judgment-Based)

Similarity scores (0.6/0.4/0.25 tiers) are guidance. Select prior knowledge based on:
- **Task complexity** (more priors for complex tasks)
- **Track record** (prefer high helped/failed ratio)
- **Contextual relevance** (semantic similarity is one signal, not the only signal)

---

## Shared Patterns

### INIT_PATTERN

Reusable initialization for both TASK and CAMPAIGN flows.

```
EMIT: STATE_ENTRY state=INIT [mode={mode}]
DO: mkdir -p .ftl && echo "${CLAUDE_PLUGIN_ROOT}" > .ftl/plugin_root
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear
EMIT: PHASE_TRANSITION from=init to=explore
GOTO: EXPLORE
```

### EXPLORE_PATTERN

Reusable exploration logic for both TASK and CAMPAIGN flows.

```
EMIT: STATE_ENTRY state=EXPLORE agents=4
DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
    - Task(ftl:ftl-explorer) "mode=structure"
    - Task(ftl:ftl-explorer) "mode=pattern, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=memory, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=delta, objective={objective}"
WAIT: All 4 complete OR timeout=300s (quorum=3)
  CHECK: python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py wait-explorers --required=3 --timeout=300
  IF: wait_result=="quorum_met" OR wait_result=="all_complete" → PROCEED
  IF: wait_result=="timeout" → EMIT: PARTIAL_FAILURE missing={missing}, PROCEED
  IF: wait_result=="quorum_failure" → GOTO ERROR with error_type="quorum_failure"
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{objective}"
DO: | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
# Output: .ftl/exploration.json (aggregated from .ftl/cache/explorer_*.json)
EMIT: PHASE_TRANSITION from=explore to=plan
GOTO: PLAN
```

### PLAN_PATTERN

Reusable planning logic with decision parsing.

```
EMIT: STATE_ENTRY state=PLAN
TRACK: clarify_count (starts at 0, persists across PLAN re-entries)
IF: clarify_count > 5 → EMIT: "Max clarifications (5) reached", RETURN with questions summary
DO: Task(ftl:ftl-planner) with {input} + exploration.json > plan_output.md
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/decision_parser.py plan_output.md > decision.json
CHECK: decision=$(jq -r .decision decision.json)
IF: decision=="CLARIFY" → INCREMENT clarify_count, present questions, ASK user, GOTO PLAN
IF: decision=="CONFIRM" → present selection, confirm with user, GOTO PLAN
# Note: CONFIRM has no counter - assumes user explicitly wants confirmation loop
IF: decision=="PROCEED" → extract plan_json to plan.json, GOTO {next_state}
IF: decision=="UNKNOWN" → EMIT: "Decision unclear, defaulting to CLARIFY", GOTO PLAN
```

### ERROR_PATTERN

Handles orchestration failures gracefully.

```
STATE: ERROR
  EMIT: STATE_ENTRY state=ERROR error_type={type}
  IF: error_type=="timeout" → EMIT: "Exploration timeout, using partial data", GOTO PLAN
  IF: error_type=="quorum_failure" → EMIT: "Insufficient explorer data", RETURN with partial results
  IF: error_type=="cascade_stuck" → DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-analysis, RETURN with analysis
  DEFAULT: EMIT: "Unrecoverable error: {type}", RETURN with error summary
```

---

## TASK State Machine

```
STATE: INIT
  USE: INIT_PATTERN

STATE: EXPLORE
  USE: EXPLORE_PATTERN with objective={task}

STATE: PLAN
  USE: PLAN_PATTERN with input={task}, next_state=BUILD

STATE: BUILD
  EMIT: STATE_ENTRY state=BUILD
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan plan.json
  DO: Task(ftl:ftl-builder) with workspace path
  EMIT: PHASE_TRANSITION from=build to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  DO: Task(ftl:ftl-observer)  # Analyzes all workspaces in .ftl/workspace/
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE

STATE: COMPLETE
  EMIT: STATE_ENTRY state=COMPLETE
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/phase.py transition complete
  EMIT: "Task complete. See .ftl/workspace/ for deliverables."
  RETURN: Summary to user

STATE: ERROR
  USE: ERROR_PATTERN
```

---

## CAMPAIGN State Machine

```
STATE: INIT
  USE: INIT_PATTERN with mode=campaign

STATE: EXPLORE
  USE: EXPLORE_PATTERN with objective={objective}

STATE: PLAN
  USE: PLAN_PATTERN with input={objective}, next_state=REGISTER

STATE: REGISTER
  EMIT: STATE_ENTRY state=REGISTER
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective"
  DO: cat plan.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks
  EMIT: PHASE_TRANSITION from=register to=execute
  GOTO: EXECUTE

STATE: EXECUTE
  EMIT: STATE_ENTRY state=EXECUTE
  TRACK: iteration_count (starts at 0, persists across EXECUTE re-entries)
  TRACK: prior_ready_count (persists across EXECUTE re-entries)
  IF: iteration_count > 20 → EMIT: "Max iterations (20) reached", GOTO CASCADE
  INCREMENT: iteration_count
  DO: ready_tasks = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks
  EMIT: READY_TASKS count={len(ready_tasks)}, iteration={iteration_count}
  IF: ready_tasks is empty → EMIT: PHASE_TRANSITION from=execute to=cascade, GOTO CASCADE
  IF: iteration_count > 3 AND len(ready_tasks) == prior_ready_count → EMIT: "Stuck: ready_tasks unchanged for 3+ iterations", GOTO CASCADE
  SET: prior_ready_count = len(ready_tasks)
  DO: FOR EACH task in ready_tasks (launch in PARALLEL):
        cat plan.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan - --task {SEQ}
        Task(ftl:ftl-builder) with workspace
        python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ complete|blocked
  GOTO: EXECUTE

STATE: CASCADE
  EMIT: STATE_ENTRY state=CASCADE
  DO: cascade = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status

  # Adaptive re-planning: if significant tasks affected, attempt recovery
  IF: cascade.state == "stuck" AND len(cascade.unreachable) >= 2 →
      EMIT: CASCADE_REPLAN affected={len(cascade.unreachable)}
      DO: replan_input = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py get-replan-input
      DO: Task(ftl:ftl-planner) with replan_input > revised_plan.json
      IF: revised_plan valid →
          DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py merge-revised-plan revised_plan.json
          EMIT: PHASE_TRANSITION from=cascade to=execute
          GOTO: EXECUTE

  # Fallback: propagate blocks and observe (original behavior)
  IF: cascade.state == "stuck" →
      EMIT: CASCADE_PROPAGATE
      DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks

  EMIT: PHASE_TRANSITION from=cascade to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  SKIP_IF: All tasks blocked with same root cause (single failure cascaded)
  DO: Task(ftl:ftl-observer)
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE

STATE: COMPLETE
  EMIT: STATE_ENTRY state=COMPLETE
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/phase.py transition complete
  DO: summary = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py summary
  EMIT: "Campaign complete. {summary.complete_count} complete, {summary.blocked_count} blocked."
  RETURN: Summary to user
```

---

## Workspace Lifecycle

```
.ftl/workspace/NNN_slug_status.xml
```

Workspace transitions: `active` → `complete` | `blocked`

**Blocking captures failure state for learning** - The workspace records what failed and why.
Blocking is not system failure; it's success at information capture for Observer pattern extraction.

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
  1. Get all tasks with task_state = "pending"
  2. For each pending task:
     - Get depends[] list
     - If depends is empty or "none" → ready
     - If ALL depends have task_state = "complete" → ready
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
     - Set task_state = "blocked"
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
  "framework_confidence": "number | null",
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

- [references/CLI_REFERENCE.md](references/CLI_REFERENCE.md) - Complete command syntax
- [references/MEMORY_SEMANTICS.md](references/MEMORY_SEMANTICS.md) - Memory decay, feedback, and graph traversal
