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

Phases: `EXPLORE → PLAN → BUILD (loop with stall recovery) → LEARN → COMPLETE`

**Fast path:** If the objective is a single-file change with obvious scope (rename, config tweak, small fix), skip EXPLORE/PLAN. Spawn one builder directly with the objective as its task. LEARN phase still applies — store at least one insight if work was completed.

### EXPLORE

**Goal:** Understand the codebase landscape for this objective.

**Greenfield fast path:** If `git ls-files | wc -l` returns 0 or only config files, skip exploration and proceed to PLAN with `EXPLORATION: {}`.

**Standard path:**

1. **Discover structure:** `git ls-files | head -80` — identify 3-6 natural partitions (by directory, module, or layer).

2. **Spawn explorer swarm** (haiku, parallel, background): one Task per partition with `subagent_type="helix:helix-explorer"`, `model=haiku`, `max_turns=8`, `run_in_background=true`. Prompt: `SCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: {objective}`. Track `EXPLORER_COUNT=N`.

3. **Wait and merge:**
   ```bash
   python3 "$HELIX/lib/build_loop.py" wait-for-explorers --count $EXPLORER_COUNT --timeout 90
   ```
   Returns JSON with `completed`, `findings` (merged, deduped by file path), and partial results on timeout.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Spawn planner** (opus, **foreground**): `subagent_type="helix:helix-planner"`, `max_turns=12`. Prompt: `OBJECTIVE: {objective}\nEXPLORATION: {findings_json}`. Insights are auto-injected via hook.

2. **Parse PLAN_SPEC** from returned result — extract the JSON array after `PLAN_SPEC:`.

3. **Create tasks from PLAN_SPEC:** `TaskCreate(subject="{seq}: {slug}", description=..., activeForm="Building {slug}", metadata={"seq": "{seq}", "relevant_files": [...]})`. Track `seq_to_id[spec.seq] = task_id`.

4. **Set dependencies:** `TaskUpdate(taskId=seq_to_id[spec.seq], addBlockedBy=[seq_to_id[b], ...])`.

5. **Validate DAG** (in-context, no CLI): verify acyclic (walk dependencies), confirm `relevant_files` reference paths from exploration findings.

If PLAN_SPEC empty or ERROR — add exploration context, re-run planner.

### BUILD

**Goal:** Execute tasks, collect insights from outcomes.

#### Memory Injection

**Inject per wave, not per task.** `batch_inject` recalls insights for all ready tasks in one call, automatically diversifying so parallel builders get different insights:

```bash
python3 "$HELIX/lib/injection.py" batch-inject --tasks '$OBJECTIVES_JSON' --limit 5
```

Returns `{"results": [{"insights": [...], "names": [...]}, ...], "total_unique": N}`. The `INJECTED` line in builder prompts enables feedback attribution. If `batch_inject` is skipped, the SubagentStart hook provides fallback injection.

#### Spawning Builders

Spawn with `subagent_type="helix:helix-builder"`, `max_turns=25`, `run_in_background=true` (omit for single foreground task). Prompt format uses `format_prompt()` fields: TASK_ID, TASK, OBJECTIVE, VERIFY, RELEVANT_FILES, insights, INJECTED.

**Background wait:**
```bash
python3 "$HELIX/lib/build_loop.py" wait-for-builders --task-ids "2,3" --timeout 90
```
Returns `completed`, `delivered`, `blocked`, `unknown`, `all_delivered`. Crashed agents land in `unknown` — re-dispatch or resolve.

#### Build Loop

```
while pending tasks exist:
    1. Identify ready tasks: pending tasks whose blockedBy are all delivered (in-context filter)
    2. If none ready but pending remain → STALLED recovery (see below)
    3. Batch inject insights for ready tasks
    4. Assemble PARENT_DELIVERIES from wave results (in-context: format "[task_id] summary" for each delivered blocker)
    5. Spawn builders (cap at 6 per wave — more risks file contention)
    6. Wait for wave completion
    7. If `insights_emitted > 0` in wait result, builders already captured task-level insights
    8. Process results, update task status
```

**STALLED recovery:** Analyze the stall. If one task is blocked with an obvious workaround, SKIP it (`TaskUpdate(task_id, status="completed", metadata={helix_outcome: "skipped"})`) and store the failure insight. If systemic, ABORT and store insight. If verify was unclear, REPLAN. After 3+ attempts on the same blocker, ABORT and escalate.

**On unknown/crashed:** Re-dispatch. If a task crashes twice, mark blocked and surface in LEARN.

### LEARN

**Goal:** Capture session-level insights that builders cannot see.

Builders see one task. You see the whole session: which plans worked, which stalled, what patterns emerged across tasks. **This is not optional.**

If `insights_emitted > 0` from wait-for-builders, builders already stored task-level insights. Focus LEARN on cross-task patterns they couldn't see: plan failures, dependency ordering, scope issues.

```bash
python3 "$HELIX/lib/memory/core.py" store \
  --content "When modifying the auth module, run both unit AND integration tests" \
  --tags '["testing", "auth"]'
```

Store systemic patterns, planning insights, exploration gaps, session discoveries. Test: would this help a developer 3 months from now? **Minimum:** at least one insight per session that completed work.

### COMPLETE

Verify: run `health` — confirm `recent_feedback > 0`. If 0 despite injection, check `extraction.log`.

---

**NEVER use TaskOutput** — dumps 70KB+ execution traces. Agent contracts in `agents/*.md`.
