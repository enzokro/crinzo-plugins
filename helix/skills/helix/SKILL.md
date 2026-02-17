---
name: helix
description: Self-learning orchestrator with unified insight memory. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

This file (created by SessionStart hook) contains the plugin root path with `lib/`, `agents/` subdirectories.

---

## Your Workflow

Phases: `EXPLORE → RECALL → PLAN → BUILD (loop with stall recovery) → LEARN → COMPLETE`

**Fast path:** If the objective is a single-file change with obvious scope (rename, config tweak, small fix), skip EXPLORE/PLAN. Spawn one builder directly with the objective as its task. LEARN phase still applies — store at least one insight if work was completed.

### EXPLORE

**Goal:** Understand the codebase landscape for this objective.

**Greenfield fast path:** If `git ls-files | wc -l` returns 0 or only config files, skip exploration and proceed to PLAN with `EXPLORATION: {}`.

**Standard path:**

1. **Discover structure:** `git ls-files | head -80` — identify 3-6 natural partitions (by directory, module, or layer).

2. **Spawn explorer swarm** (sonnet, foreground parallel): one Task per partition with `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. Prompt: `SCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: {objective}`. **All explorers in ONE message — no `run_in_background`.** They execute concurrently and all return before your next turn.

3. **Merge findings:** Parse each Task's return value for the explorer JSON. Merge and dedup findings by file path. On explorer crash/error, proceed with findings from successful explorers.

### RECALL

**Goal:** Bring the orchestrator's own accumulated knowledge to bear on this session.

```bash
python3 "$HELIX/lib/memory/core.py" recall "{objective_summary}" --limit 5
```

If insights are returned, reason about their strategic implications — not the tactical advice itself (planners/builders get that via hooks), but what the insights mean for **how to orchestrate**:

- **Decomposition constraints** — areas that must stay atomic, known tight coupling between modules
- **Verification requirements** — tests or checks that past experience proved necessary
- **Risk areas** — modules that historically block or require multiple attempts
- **Sequencing hints** — dependency orderings that succeeded or failed

Synthesize into a `CONSTRAINTS` block for the planner prompt. Example:

```
CONSTRAINTS:
- Keep auth middleware changes atomic (historically blocks when split across tasks)
- Plan explicit mock setup task before any OAuth integration tests
- The payments module requires integration tests — verify command must include them
```

**If recall returns empty** (cold start or no relevant matches): omit `CONSTRAINTS`. Planner operates as before — no degradation.

**Fast path:** Skip RECALL. Single-file changes don't benefit from strategic memory.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Spawn planner** (opus, **foreground**): `subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt: `OBJECTIVE: {objective}\nEXPLORATION: {findings_json}\nCONSTRAINTS: {constraints_from_recall}`. Omit CONSTRAINTS if RECALL returned empty. Tactical insights are auto-injected via hook.

2. **Parse PLAN_SPEC** from returned result — extract the JSON array after `PLAN_SPEC:`.

3. **Create tasks from PLAN_SPEC:** `TaskCreate(subject="{seq}: {slug}", description=..., activeForm="Building {slug}", metadata={"seq": "{seq}", "relevant_files": [...]})`. Track `seq_to_id[spec.seq] = task_id`.

4. **Set dependencies:** `TaskUpdate(taskId=seq_to_id[spec.seq], addBlockedBy=[seq_to_id[b], ...])`.

5. **Validate DAG:**
   ```bash
   python3 "$HELIX/lib/build_loop.py" detect-cycles --dependencies '$DEPS_JSON'
   ```
   Confirm `relevant_files` reference paths from exploration findings.

If PLAN_SPEC empty or ERROR — add exploration context, re-run planner.

### BUILD

**Goal:** Execute tasks, collect insights from outcomes.

#### Memory Injection

**Inject per wave, not per task.** `batch_inject` recalls insights for all ready tasks in one call, automatically diversifying so parallel builders get different insights:

```bash
python3 "$HELIX/lib/injection.py" batch-inject --tasks '$OBJECTIVES_JSON' --limit 5
```

Returns `{"results": [{"insights": [...], "names": [...]}, ...], "total_unique": N}`. The `INJECTED` line in builder prompts enables feedback attribution.

#### Spawning Builders

Spawn with `subagent_type="helix:helix-builder"`, `max_turns=250`. Prompt format uses `format_prompt()` fields: TASK_ID, TASK, OBJECTIVE, VERIFY, RELEVANT_FILES, insights, INJECTED.

**Foreground parallel:** All builders for a wave go in ONE message — no `run_in_background`. They execute concurrently and all return before your next turn. Parse DELIVERED/BLOCKED/PARTIAL outcomes directly from each Task's return value. Crashed agents return errors — visible immediately.

#### Build Loop

```
while pending tasks exist:
    ready = build_loop.py status --tasks "$(TaskList as JSON)"  →  {ready, stalled, stall_info}
    If stalled → STALLED recovery (below)
    Batch inject → assemble PARENT_DELIVERIES ("[task_id] summary" per delivered blocker)
    Spawn builders (cap 6/wave; deep DAGs: narrow 2-3 with rapid succession)
      — all in ONE message, NO run_in_background
    Each Task returns → parse DELIVERED/BLOCKED → TaskUpdate outcomes
    Sanity-check: did deliveries change downstream assumptions?
```

**STALLED recovery:** First, recall insights about the blocked area:
```bash
python3 "$HELIX/lib/memory/core.py" recall "{blocked_task_description}" --limit 3
```
Use any returned insights to inform the recovery strategy — the system may have seen this stall pattern before. Then analyze the stall:
- **One task, obvious workaround:** SKIP it (TaskUpdate status="completed", metadata={helix_outcome: "skipped"}) and store failure insight.
- **Blocked subtree, fixable scope:** Re-plan the blocked task and its dependents only. Create replacement tasks wired to the same predecessors. Do NOT replan the entire DAG.
- **Verify was unclear or wrong:** REPLAN with tighter verification constraints.
- **Systemic or 3+ attempts on same blocker:** ABORT and escalate to user.

**On PARTIAL:** Fold the REMAINING work into a new task in the next wave. Do not re-dispatch the entire original task.

**On unknown/crashed:** Re-dispatch. If a task crashes twice, mark blocked and surface in LEARN.

### LEARN

**Not optional.** You see cross-task patterns builders cannot: plan failures, dependency ordering, scope issues. Three steps: observe, ask, store. Builders already store task-level insights via hooks — your job is cross-task and strategic patterns.

#### Step 1: Observe

Review all outcomes internally. Note: which tasks blocked and why, which needed retries, what ordering/scope issues emerged, what the user might know that you don't. Formulate hypotheses. **Do not store anything yet.**

#### Step 2: Ask

Present your observations and hypotheses to the user via `AskUserQuestion`. The user holds domain knowledge, business rules, and historical context inaccessible to the system. Their answer informs what you store — ask first, store after.

**When to ask:**

| Outcome | Ask? | Rationale |
|---|---|---|
| Fast-path single builder, DELIVERED | No | Trivial; not worth interrupting |
| Any BLOCKED or PARTIAL | Yes | Highest learning value — user knows *why* |
| All DELIVERED (multi-task) | Yes | Approach/ordering insights |

**Question design — options do the cognitive work.** Encode your hypotheses as options derived from block reasons, relevant files, and task context. The user confirms, corrects, or provides their own answer via "Other".

BLOCKED/PARTIAL example — hypothesize root cause:
```
AskUserQuestion([{
  question: "Builder for '003: migrate-auth-tokens' was blocked: test suite timed out on OAuth flows. Most likely cause?",
  header: "Root cause",
  options: [
    {label: "Rate limiting", description: "Test environment has API rate limits that CI hits"},
    {label: "Missing mock", description: "These tests need a mock provider, not the real endpoint"},
    {label: "Config issue", description: "Test environment OAuth config is wrong or stale"}
  ],
  multiSelect: false
}]
```

All DELIVERED example — probe for hidden issues:
```
AskUserQuestion([{
  question: "All 4 tasks delivered. The auth module needed 2 attempts (stall recovery). Worth remembering anything about this area?",
  header: "Reflection",
  options: [
    {label: "Known friction", description: "This module has patterns/constraints that should be documented"},
    {label: "Ordering issue", description: "Tasks should have been sequenced differently"},
    {label: "All good", description: "No corrections — stall recovery handled it fine"}
  ],
  multiSelect: false
}])
```

#### Step 3: Store

Synthesize orchestrator observations + user response into insights.

- **User selects option or types "Other"**: Combine your observation with their answer into a "When X, do Y because Z" insight. Tag with `user-provided`.
  ```bash
  python3 "$HELIX/lib/memory/core.py" store \
    --content "When testing OAuth token migration, use mock provider for unit tests because the test OAuth provider rate-limits at 10 req/s and blocks CI" \
    --tags '["user-provided", "testing", "auth"]'
  ```
- **User dismisses** ("All good" / equivalent): Fall back to your own cross-task observations. Store as before without `user-provided` tag.
- **Skipped ask** (fast-path): Store your own observations directly.

Test: would this help a developer 3 months from now? **Minimum:** one insight per session that completed work.

### COMPLETE

Summarize: tasks delivered, tasks blocked, insights stored (noting which were user-informed). If all tasks blocked, surface the pattern.

---

Agent contracts in `agents/*.md`.
