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

2. **Spawn explorer swarm** (sonnet, foreground parallel): one Task per partition with `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. Prompt: `SCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: {objective}`. **All explorers in ONE message — no `run_in_background`.** They execute concurrently and all return before your next turn.

3. **Merge findings:** Parse each Task's return value for the explorer JSON. Merge and dedup findings by file path. On explorer crash/error, proceed with findings from successful explorers.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Spawn planner** (opus, **foreground**): `subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt: `OBJECTIVE: {objective}\nEXPLORATION: {findings_json}`. Insights are auto-injected via hook.

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

**STALLED recovery:** Analyze the stall:
- **One task, obvious workaround:** SKIP it (TaskUpdate status="completed", metadata={helix_outcome: "skipped"}) and store failure insight.
- **Blocked subtree, fixable scope:** Re-plan the blocked task and its dependents only. Create replacement tasks wired to the same predecessors. Do NOT replan the entire DAG.
- **Verify was unclear or wrong:** REPLAN with tighter verification constraints.
- **Systemic or 3+ attempts on same blocker:** ABORT and escalate to user.

**On PARTIAL:** Fold the REMAINING work into a new task in the next wave. Do not re-dispatch the entire original task.

**On unknown/crashed:** Re-dispatch. If a task crashes twice, mark blocked and surface in LEARN.

### LEARN

**Not optional.** You see cross-task patterns builders cannot: plan failures, dependency ordering, scope issues. Focus here; builders already store task-level insights.

```bash
python3 "$HELIX/lib/memory/core.py" store \
  --content "When modifying the auth module, run both unit AND integration tests" \
  --tags '["testing", "auth"]'
```

Test: would this help a developer 3 months from now? **Minimum:** one insight per session that completed work.

### COMPLETE

Summarize: tasks delivered, tasks blocked, insights stored. If all tasks blocked, surface the pattern.

---

Agent contracts in `agents/*.md`.
