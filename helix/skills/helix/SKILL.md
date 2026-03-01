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

Phases: `RECALL → EXPLORE → PLAN → BUILD (loop with stall recovery) → LEARN → COMPLETE`

**Fast path:** If the objective is a single-file change with obvious scope (rename, config tweak, small fix), skip EXPLORE/PLAN. Spawn one builder directly with the objective as its task. LEARN phase still applies.

### RECALL

**Goal:** Bring accumulated knowledge to bear on orchestration decisions.
**Exit when:** Synthesis blocks ready (empty blocks omitted).

```bash
python3 "$HELIX/lib/injection.py" strategic-recall "{objective_summary}"
```

Parse JSON. Use `summary` for triage, synthesize `insights` into blocks:

1. **CONSTRAINTS** — proven insights (`_effectiveness >= 0.70`): decomposition rules, verification needs, sequencing.
2. **RISK_AREAS** — risky insights (`_effectiveness < 0.40`) or `derived`/`failure` tags: flag for extra verification, smaller tasks.
3. **EXPLORATION_TARGETS** — areas referenced by insights that expand scope beyond the naive objective.
4. **GRAPH_DISCOVERED** — `_hop: 1` insights (graph-adjacent, not direct match). Treat as exploration targets.

**Weight by relevance:** An insight with `_effectiveness: 0.85` but `_relevance: 0.36` (barely above threshold) is weakly connected to this objective — treat as background context, not hard constraint. High-effectiveness + high-relevance = strong constraint.

**Triage signals:** `coverage_ratio > 0.3` = well-mapped, trust constraints. `< 0.1` = uncharted, expand exploration. `graph_expanded_count > 0` = graph surfacing related context.

Example:
```
CONSTRAINTS:
- Keep auth middleware changes atomic (historically blocks when split) [82%]
- Plan explicit mock setup task before OAuth integration tests [75%]

RISK_AREAS:
- Payments module has blocked 3 of 4 attempts — use smaller tasks [35%]

EXPLORATION_TARGETS:
- config/secrets.py (referenced by auth insights but not in objective)
- tests/fixtures/ (multiple insights reference test setup patterns)
```

**Targeted follow-up:** If blind spots identified, call `python3 "$HELIX/lib/memory/core.py" recall "{specific_area}" --limit 3`.
**If empty:** omit blocks, no degradation. **Fast path:** skip RECALL for single-file changes.

### EXPLORE

**Goal:** Map codebase landscape, leveraging recalled insights.
**Exit when:** Partitioned findings cover files relevant to objective.
**Greenfield:** If `git ls-files | wc -l` returns 0 or only config files, skip to PLAN with `EXPLORATION: {}`.
1. `git ls-files | head -80` — identify 3-6 natural partitions.
2. Spawn explorer swarm: `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. Prompt: `CONTEXT:{relevant_insights}\nSCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: {objective}`. **All explorers in ONE message — no `run_in_background`.**
3. Merge findings by file path. Proceed with successful explorers on crash/error.

### PLAN

**Goal:** Decompose objective into executable task DAG.
**Exit when:** Tasks created with valid dependencies and no cycles.

1. Spawn planner: `subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt: `OBJECTIVE: {objective}\nEXPLORATION: {findings_json}\nCONSTRAINTS: {constraints_from_recall}\nRISK_AREAS: {risk_areas_from_recall}`. Omit empty blocks.
2. Parse PLAN_SPEC JSON array from result.
3. Create tasks: `TaskCreate(subject="{seq}: {slug}", description=..., activeForm="Building {slug}", metadata={"seq": "{seq}", "relevant_files": [...]})`. Track `seq_to_id[spec.seq] = task_id`.
4. Set dependencies: `TaskUpdate(taskId=seq_to_id[spec.seq], addBlockedBy=[seq_to_id[b], ...])`.
5. Validate: `python3 "$HELIX/lib/build_loop.py" detect-cycles --dependencies '$DEPS_JSON'`. Confirm relevant_files reference exploration paths.

If PLAN_SPEC empty or ERROR -- add exploration context, re-run planner.

### BUILD

**Goal:** Execute all tasks. **Exit when:** no pending tasks remain.

#### Build Loop

```
while pending tasks:
    status → {ready, stalled, stall_info}
    If stalled → recovery (below)
    Batch inject memory for ready tasks:
        python3 "$HELIX/lib/injection.py" batch-inject --tasks '$OBJECTIVES_JSON' --limit 3
    Assemble PARENT_DELIVERIES ("[task_id] summary" per delivered blocker)
    Spawn builders (cap 6/wave): subagent_type="helix:helix-builder", max_turns=250
      — all in ONE message, NO run_in_background
    Parse DELIVERED/BLOCKED/PARTIAL → TaskUpdate outcomes
```

**On PARTIAL:** Fold REMAINING into new task next wave. Don't re-dispatch entire original.
**On crash:** Re-dispatch once. Second crash → mark blocked.

#### Stall Recovery

Recall insights about the blocked area: `python3 "$HELIX/lib/memory/core.py" recall "{blocked_task_description}" --limit 5 --graph-hops 1`

Then analyze:
- **One task, obvious workaround:** SKIP (TaskUpdate completed + metadata={helix_outcome: "skipped"}) and store failure insight.
- **Blocked subtree, fixable scope:** Re-plan just the blocked task and dependents. Wire replacement tasks to same predecessors. Don't replan entire DAG.
- **Verify was unclear/wrong:** REPLAN with tighter verification.
- **3+ attempts on same blocker:** ABORT and escalate to user.

### LEARN

**Not optional.** You see cross-task patterns builders cannot. **Exit when:** at least one insight stored (or user dismisses).

#### Step 1: Observe

Review all outcomes. Collect per task: exact outcome text, relevant_files, verify command, retry count, errors. Note cross-task patterns. Formulate hypotheses. **Do not store yet.**

For BLOCKED tasks, check insight ancestry if insights were injected:
```bash
python3 "$HELIX/lib/memory/core.py" neighbors "{insight_name}" --relation led_to --limit 3
```
If the injected insight has `led_to` provenance from low-effectiveness ancestors, note this — the insight lineage may be propagating an error pattern.

#### Step 2: Ask

Present observations to user via `AskUserQuestion` -- they hold domain knowledge inaccessible to the system.

**When to ask:** Any BLOCKED/PARTIAL -- yes (highest learning value). All DELIVERED multi-task -- yes (approach insights). Fast-path single DELIVERED -- skip.

**Question construction rules:**

1. **Quote, don't paraphrase.** Include actual error/outcome text. Never a question without it.
2. **Name the files.** Specific paths from relevant_files or error output. Not "test suite timed out" -- "`tests/auth/test_oauth.py` timed out."
3. **Evidence-grounded options.** Each option states supporting evidence. Not restated labels.
4. **One question per blocked/notable task.** Up to 4 slots. Never merge distinct failures into one vague question.

BLOCKED/PARTIAL example:
```
AskUserQuestion([{
  question: "Builder for '003: migrate-auth-tokens' was BLOCKED: 'ConnectionTimeout after 30s in tests/auth/test_oauth.py:42 — OAuth provider unreachable'. Files: src/auth/tokens.py, tests/auth/test_oauth.py. Verify was: pytest tests/auth/ -k oauth_migration. Most likely cause?",
  header: "Root cause: 003",
  options: [
    {label: "Missing mock", description: "test_oauth.py hits real OAuth endpoint — ConnectionTimeout suggests no mock configured for this test flow"},
    {label: "Network/env config", description: "OAuth provider URL may be wrong in test config — 30s timeout implies connection attempt, not auth failure"},
    {label: "Dependency ordering", description: "Token migration requires auth-service running — another task should have set up test fixtures first"}
  ],
  multiSelect: false
}])
```

All DELIVERED (with friction) example:
```
AskUserQuestion([{
  question: "All 4 tasks delivered. '002: refactor-auth-middleware' needed 2 attempts — first failed on tests/middleware/test_chain.py (assertion: expected 3 middleware layers, got 2). After stall recovery, builder added missing CORS layer. Is this a known constraint?",
  header: "Reflection: 002",
  options: [
    {label: "Document constraint", description: "Middleware chain order matters — CORS must be explicit. The layer-count assertion in test_chain.py is the contract"},
    {label: "Test was brittle", description: "test_chain.py counts layers instead of asserting behavior — breaks on any refactor that changes layer count"},
    {label: "All good", description: "Stall recovery handled it correctly, nothing to remember"}
  ],
  multiSelect: false
}])
```

#### Step 3: Store

- **User selects option or types "Other"**: Combine observation with their answer. Tag `user-provided`.
  ```bash
  python3 "$HELIX/lib/memory/core.py" store \
    --content "When modifying auth middleware in src/auth/middleware.py, always include explicit CORS layer — test_chain.py validates 3-layer stack and implicit CORS from Flask-CORS doesn't count" \
    --tags '["user-provided", "auth", "middleware"]'
  ```
- **User dismisses**: Fall back to your own cross-task observations. Store without `user-provided` tag.
- **Skipped ask** (fast-path): Store your own observations directly.

Insights auto-link (similarity >= 0.60) and provenance edges form during extraction. Test: would this help 3 months from now? **Minimum:** one insight per session.

### COMPLETE

Summarize: tasks delivered, tasks blocked, insights stored (noting which were user-informed). If all tasks blocked, surface the pattern.

---

Agent contracts in `agents/*.md`.
