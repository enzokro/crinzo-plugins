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
| **Builder** | Transform spec into code | opus | 5-9 |
| **Observer** | Extract patterns from work | opus | 10 |

## Paths

**Orchestrator commands** (this file) use `${CLAUDE_PLUGIN_ROOT}` - available in the main session.

**Sub-agent commands** (agent/*.md files) use `$(cat .ftl/plugin_root)` - sub-agents spawned via
Task tool do NOT inherit environment variables. The `setup-env.sh` hook writes the plugin path
to `.ftl/plugin_root` at session start, allowing sub-agents to locate the plugin.

See the CLI docs: [references/CLI_REFERENCE.md](references/CLI_REFERENCE.md) for complete syntax.

## Hooks

FTL uses Claude Code hooks for session lifecycle management and mid-campaign learning:

| Hook | Trigger | Script | Purpose |
|------|---------|--------|---------|
| PreToolUse (session start) | First tool invocation | `setup-env.sh` | Create venv, persist plugin_root |
| PostToolUse (session end) | Session cleanup | `cleanup-env.sh` | Log session, cleanup |
| PostToolUse (inject-learning) | Bash commands | `inject-learning.sh` | Extract failures mid-campaign |

**inject-learning.sh**: Monitors builder tool output during campaigns. When a task blocks, extracts
failure patterns and injects them into subsequent workspaces via `sibling_failures`. This enables
parallel branches to learn from each other's failures within a single campaign execution.

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

## Architecture: Two-Layer State Model

FTL uses a single state system with campaign.status as the source of truth:

| Layer | Location | Purpose | States |
|-------|----------|---------|--------|
| **Orchestration DSL** | This file | Guide Claude's behavioral flow | INIT, EXPLORE, PLAN, REGISTER, EXECUTE, CASCADE, BUILD, OBSERVE, COMPLETE, ERROR |
| **Campaign Status** | `campaign.py` | Track workflow status in database | active, complete |

**Design principle**: Campaign status IS the workflow state. The orchestration DSL states are behavioral prompts that guide flow, while campaign.status provides persistent, queryable state for tooling.

**Key distinction**: REGISTER, EXECUTE, and CASCADE exist only in this DSL—they're campaign management behaviors. The campaign table tracks task completion, blocks, and overall campaign status.

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
# Clear stale workspaces from completed campaigns to prevent workspace_id collisions
DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py clear-stale
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
  IF: wait_result.status=="quorum_met" OR wait_result.status=="all_complete" → PROCEED
  IF: wait_result.status=="timeout" → EMIT: PARTIAL_FAILURE missing={wait_result.missing}, PROCEED
  IF: wait_result.status=="quorum_failure" → GOTO ERROR with error_type="quorum_failure"
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
CHECK: validation=$(jq -r '.validation // {}' decision.json)
IF: decision=="CLARIFY" → INCREMENT clarify_count, present questions, ASK user, GOTO PLAN
IF: decision=="CONFIRM" → present selection, confirm with user, GOTO PLAN
# Note: CONFIRM has no counter - assumes user explicitly wants confirmation loop
IF: decision=="PROCEED" →
    # Validate plan structure before proceeding
    CHECK: is_valid=$(jq -r '.validation.valid // true' decision.json)
    IF: is_valid==false →
        CHECK: errors=$(jq -r '.validation.errors[]' decision.json)
        EMIT: PLAN_VALIDATION_FAILED errors={errors}
        INCREMENT clarify_count
        ASK user: "Plan validation failed: {errors}. Please clarify or revise."
        GOTO PLAN
    CHECK: plan_id = jq -c '.plan_json' decision.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py write | jq -r .id
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
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "{task}"

STATE: EXPLORE
  USE: EXPLORE_PATTERN with objective={task}

STATE: PLAN
  USE: PLAN_PATTERN with input={task}, next_state=BUILD

STATE: BUILD
  EMIT: STATE_ENTRY state=BUILD
  CHECK: ws_result = python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id {plan_id}
  # ws_result.created[0] contains workspace dict with workspace_id, status, etc.
  DO: workspace_id = ws_result.created[0].workspace_id
  DO: builder_output = Task(ftl:ftl-builder) with workspace_id
  # Extract UTILIZED from builder output
  DO: utilized = extract JSON array following "UTILIZED:" from builder_output (default: [])
  DO: injected = python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py get-injected {workspace_id}
  IF: workspace completed successfully →
      # Use base64 encoding to avoid shell quoting issues with JSON
      DO: utilized_b64 = base64_encode(utilized)
      DO: injected_b64 = base64_encode(injected)
      DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py feedback-batch --utilized-b64 {utilized_b64} --injected-b64 {injected_b64}
  EMIT: PHASE_TRANSITION from=build to=observe
  GOTO: OBSERVE

STATE: OBSERVE
  EMIT: STATE_ENTRY state=OBSERVE
  DO: Task(ftl:ftl-observer)  # Analyzes all workspaces in database (workspace table)
  EMIT: PHASE_TRANSITION from=observe to=complete
  GOTO: COMPLETE

STATE: COMPLETE
  EMIT: STATE_ENTRY state=COMPLETE
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
  DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "{objective}"

STATE: EXPLORE
  USE: EXPLORE_PATTERN with objective={objective}

STATE: PLAN
  USE: PLAN_PATTERN with input={objective}, next_state=REGISTER

STATE: REGISTER
  EMIT: STATE_ENTRY state=REGISTER
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
        CHECK: ws_result = python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id {plan_id} --task {SEQ}
        DO: workspace_id = ws_result.created[0].workspace_id
        DO: builder_output = Task(ftl:ftl-builder) with workspace_id
        DO: utilized = extract JSON array following "UTILIZED:" from builder_output (default: [])
        DO: injected = python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py get-injected {workspace_id}
        IF: task completed (not blocked) →
            # Use base64 encoding to avoid shell quoting issues with JSON
            DO: utilized_b64 = base64_encode(utilized)
            DO: injected_b64 = base64_encode(injected)
            DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py feedback-batch --utilized-b64 {utilized_b64} --injected-b64 {injected_b64}
        # Note: Campaign task status auto-syncs when workspace.complete() or workspace.block() is called
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
          CHECK: merge_result = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py merge-revised-plan revised_plan.json
          IF: merge_result contains "error" →
              EMIT: CASCADE_MERGE_FAILED error={merge_result.error}
              GOTO: OBSERVE  # Fall through to observation instead of infinite retry
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
  DO: status = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py status
  EMIT: "Campaign complete. {status.summary.complete} complete, {status.summary.blocked} blocked."
  RETURN: Summary to user
```

---

## Workspace Lifecycle

```
Workspace ID format: {SEQ}-{slug} (e.g., "001-add-feature")
Storage: .ftl/ftl.db (workspace table)
API returns: workspace dicts with workspace_id, status, delta, verify, etc.
```

States: `active` → `complete` | `blocked`

**Blocking = success**: Captures failure state for learning. Observer extracts patterns from blocked workspaces.

### State Synchronization

Workspace operations are the **single source of truth** for task status:

| Workspace Operation | Effect |
|---------------------|--------|
| `workspace.complete()` | Sets workspace status to "complete" AND syncs campaign task status |
| `workspace.block()` | Sets workspace status to "blocked" AND syncs campaign task status |

This design makes state desync **impossible** — there's only one API to call, and it maintains consistency automatically. The orchestrator does not need to separately update campaign task status.

### Campaign Grounding

Workspaces are bound to the active campaign via `campaign_id` foreign key:

- **Creation**: `workspace.create()` validates workspace belongs to active campaign
- **Collision detection**: If workspace_id exists from a different campaign, creation fails with error
- **Cleanup**: `workspace.py clear-stale` removes workspaces from completed campaigns (called in INIT_PATTERN)

This prevents stale workspace references when task slugs repeat across campaigns.

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
      "creates": ["string (optional, new files to create)"],
      "verify": "string (required)",
      "budget": "number (required)",
      "depends": "string | string[] | 'none'"
    }
  ]
}
```

**Required fields**: objective, tasks[].seq, tasks[].delta, tasks[].verify

**Optional fields**:
- `creates`: Files that will be created by this task. Listed files are exempt from delta existence validation, enabling BUILD tasks that create new files rather than modify existing ones.

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
