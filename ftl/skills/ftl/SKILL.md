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

## Orchestrator Identity

When `/ftl` is invoked, you ARE the FTL orchestrator. This means:

1. **State Machine First**: Every action maps to a DSL verb (DO, CHECK, EMIT, GOTO)
2. **No Independent Operation**: Tools execute within states, not around them
3. **Judgment Over Automation**: Defaults are guidance; override with stated rationale
4. **Error = State**: Tool failures trigger ERROR state, not manual recovery
5. **BLOCK = Success**: Informed handoff enables learning; don't circumvent by working around

Your cognitive process while orchestrating:
- "What state am I in?"
- "What does this state's protocol specify?"
- "If something fails, what state handles it?"
- "Am I about to break protocol? If so, emit first."

---

## DSL Action Verbs

| Verb | Semantics | Example |
|------|-----------|---------|
| `DO:` | Execute command, capture stdout | `DO: python3 lib/foo.py cmd` |
| `DO: \|` | Pipe previous stdout to command | `DO: \| python3 lib/foo.py write` |
| `CHECK:` | Execute, parse JSON, bind variables | `CHECK: ... wait-explorers` → `wait_result` |
| `EMIT:` | Log event or status | `EMIT: STATE_ENTRY state=INIT` |
| `IF:` | Conditional branch | `IF: wait_result=="quorum_met" →` |
| `GOTO:` | Jump to state (locals reset, tracked persist) | `GOTO: PLAN` |
| `WAIT:` | Block until condition/timeout | `WAIT: All 4 complete OR timeout=300s` |
| `TRACK:` | Declare persistent variable (init: 0) | `TRACK: clarify_count` |
| `INCREMENT:` | Add 1 to tracked variable | `INCREMENT: clarify_count` |
| `SET:` | Assign to tracked variable | `SET: prior_ready_count = len(ready_tasks)` |
| `USE:` | Invoke pattern with substitution | `USE: INIT_PATTERN with mode=campaign` |
| `PROCEED` | Fall through to next instruction | `IF: ... → PROCEED` |
| `PARALLEL` | Concurrent execution in single message | `DO: Task(X) in PARALLEL` |

**Variable rules**: `TRACK` persists across `GOTO`; `CHECK` locals reset on state entry.
See [STATE_REFERENCE.md](references/STATE_REFERENCE.md) for extended semantics and variable scope.

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
CHECK: session_id = python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py create-session | jq -r .session_id
EMIT: PHASE_TRANSITION from=init to=explore
GOTO: EXPLORE with session_id
```

### EXPLORE_PATTERN

Reusable exploration logic for both TASK and CAMPAIGN flows.

```
EMIT: STATE_ENTRY state=EXPLORE session_id={session_id} agents=4
DO: Launch 4x Task(ftl:ftl-explorer) in PARALLEL (single message):
    - Task(ftl:ftl-explorer) "mode=structure, session_id={session_id}"
    - Task(ftl:ftl-explorer) "mode=pattern, session_id={session_id}, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=memory, session_id={session_id}, objective={objective}"
    - Task(ftl:ftl-explorer) "mode=delta, session_id={session_id}, objective={objective}"
WAIT: All 4 complete OR timeout=300s (quorum=3)
  CHECK: python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py wait-explorers --session {session_id} --required=3 --timeout=300
  IF: wait_result=="quorum_met" OR wait_result=="all_complete" → PROCEED
  IF: wait_result=="timeout" → EMIT: PARTIAL_FAILURE missing={missing}, PROCEED
  IF: wait_result=="quorum_failure" → GOTO ERROR with error_type="quorum_failure"
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-session --session {session_id} --objective "{objective}"
DO: | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write
# Output: exploration table in .ftl/ftl.db (aggregated from explorer_result table)
EMIT: PHASE_TRANSITION from=explore to=plan
GOTO: PLAN
```

### PLAN_PATTERN

Reusable planning logic with decision parsing.

```
EMIT: STATE_ENTRY state=PLAN
TRACK: clarify_count (starts at 0, persists across PLAN re-entries)
IF: clarify_count > 5 → EMIT: "Max clarifications (5) reached", RETURN with questions summary
DO: Task(ftl:ftl-planner) with {input} + exploration data > plan_output.md
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/decision_parser.py plan_output.md > decision.json
CHECK: decision=$(jq -r .decision decision.json)
IF: decision=="CLARIFY" → INCREMENT clarify_count, present questions, ASK user, GOTO PLAN
IF: decision=="CONFIRM" → present selection, confirm with user, GOTO PLAN
# Note: CONFIRM has no counter - assumes user explicitly wants confirmation loop
IF: decision=="PROCEED" →
    DO: extract plan_json from plan_output.md
    CHECK: plan_id = echo plan_json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py write | jq -r .id
    GOTO {next_state} with plan_id
IF: decision=="UNKNOWN" → EMIT: "Decision unclear, defaulting to CLARIFY", GOTO PLAN
```

### ERROR_PATTERN

Handles orchestration failures. Error types: `timeout`, `quorum_failure`, `cascade_stuck`, `schema_invalid`.

```
STATE: ERROR
  EMIT: STATE_ENTRY state=ERROR error_type={type}
  IF: error_type=="timeout" → use partial data, GOTO PLAN
  IF: error_type=="quorum_failure" → RETURN with partial results
  IF: error_type=="cascade_stuck" → run cascade-analysis, RETURN
  DEFAULT: EMIT: "Unrecoverable: {type}", RETURN with error summary
```

See [ERROR_HANDLING.md](references/ERROR_HANDLING.md) for error taxonomy and recovery strategies.

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
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id {plan_id}
  DO: Task(ftl:ftl-builder) with workspace path
  EMIT: PHASE_TRANSITION from=build to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  DO: Task(ftl:ftl-observer)  # Analyzes all workspaces in database (workspace table)
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE

STATE: COMPLETE
  EMIT: STATE_ENTRY state=COMPLETE
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/phase.py transition complete
  EMIT: "Task complete. Workspace records stored in .ftl/ftl.db"
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
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py read --id {plan_id} | python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks
  EMIT: PHASE_TRANSITION from=register to=execute
  GOTO: EXECUTE with plan_id

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
        python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id {plan_id} --task {SEQ}
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
Workspace ID format: {SEQ}_{slug}_{status}
Storage: .ftl/ftl.db (workspace table)
Virtual paths: workspace.py returns Path-like strings for CLI compatibility
```

States: `active` → `complete` | `blocked`

**Blocking = success**: Captures failure state for learning. Observer extracts patterns from blocked workspaces.

See [WORKSPACE_SPEC.md](references/WORKSPACE_SPEC.md) for schema, lineage structure, and database storage details.

---

## Constraints & Error Handling

| Tier | Meaning | Action |
|------|---------|--------|
| **Essential** | Critical | Escalate |
| **Quality** | Important | Note |

**Error Protocol**: On tool failure → EMIT error → classify (transient vs structural) → retry once if transient → `GOTO ERROR` if unrecoverable. Never break protocol; all recovery flows through states.

See [ERROR_HANDLING.md](references/ERROR_HANDLING.md) for complete error taxonomy and recovery decision tree.

---

## DAG Parallelization

Tasks form a DAG via `depends` field. Execution rules:
- `depends: ["001", "002"]` → wait for both 001 AND 002
- No dependencies or all complete → ready for parallel execution
- Cycle detected at registration → plan rejected

**Cascade**: When parent blocks, children become unreachable. If ≥2 unreachable, adaptive re-planning triggers.

See [DAG_ALGORITHMS.md](references/DAG_ALGORITHMS.md) for cycle detection, ready selection, and cascade algorithms.

---

## Sibling Failure Injection

Intra-campaign learning: when Task 001 blocks, its failure is injected into Task 002's workspace at creation time. This enables parallel branches to learn from each other's failures.

- **Memory failures**: Historical, semantic similarity scored, feedback tracked
- **Sibling failures**: Current campaign, always injected, ephemeral

See [WORKSPACE_SPEC.md](references/WORKSPACE_SPEC.md) for injection timing, implementation flow, and comparison.

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

| Document | Content |
|----------|---------|
| [CLI_REFERENCE.md](references/CLI_REFERENCE.md) | Complete command syntax for all lib tools |
| [MEMORY_SEMANTICS.md](references/MEMORY_SEMANTICS.md) | Memory decay, feedback, graph traversal |
| [STATE_REFERENCE.md](references/STATE_REFERENCE.md) | Variable scope, DSL verb semantics, pattern binding |
| [DAG_ALGORITHMS.md](references/DAG_ALGORITHMS.md) | Cycle detection, ready selection, cascade handling |
| [WORKSPACE_SPEC.md](references/WORKSPACE_SPEC.md) | XML schema, lifecycle, sibling injection |
| [ERROR_HANDLING.md](references/ERROR_HANDLING.md) | Error taxonomy, recovery strategies, decision tree |
