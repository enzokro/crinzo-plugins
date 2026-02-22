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

**Fast path:** If the objective is a single-file change with obvious scope (rename, config tweak, small fix), skip EXPLORE/PLAN. Spawn one builder directly with the objective as its task. LEARN phase still applies.

### RECALL

**Goal:** Bring accumulated knowledge to bear on orchestration decisions.
**Exit when:** CONSTRAINTS, RISK_AREAS, EXPLORATION_TARGETS blocks are ready (empty blocks omitted).

```bash
python3 "$HELIX/lib/injection.py" strategic-recall "{objective_summary}"
```

Parse the JSON result. Use `summary` for triage, `insights` for synthesis.

**Coverage signal:** `coverage_ratio > 0.3` = well-mapped domain, trust constraints heavily. `coverage_ratio < 0.1` = uncharted territory, expand exploration scope.

Synthesize `insights` into three blocks:

1. **CONSTRAINTS** — from proven insights (`_effectiveness >= 0.70`):
   - Decomposition constraints — areas that must stay atomic, known tight coupling
   - Verification requirements — tests that past experience proved necessary
   - Sequencing hints — dependency orderings that succeeded or failed

2. **RISK_AREAS** — from risky insights (`_effectiveness < 0.40`) or `derived`/`failure` tags:
   - Flag for extra verification, smaller tasks, explicit test setup
   - Areas that historically block or require retries

3. **EXPLORATION_TARGETS** — areas referenced by insight content/tags that expand exploration scope beyond the naive objective:
   - Modules mentioned in insights that aren't obvious from the objective
   - Cross-cutting concerns flagged by tag distribution

4. **GRAPH_DISCOVERED** — insights with `_hop: 1` (reached via graph relationships, not direct semantic match). These surface connections the query alone wouldn't find. Treat as exploration targets — the graph says "this area is related."

**Graph signal:** `graph_expanded_count > 0` = memory graph is surfacing related context. `graph_expanded_count == 0` with edges in system = query is in an isolated topic cluster.

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

**Optional targeted follow-up:** If blind spots identified (e.g., tag distribution shows "database" but no "migration" insights), call `python3 "$HELIX/lib/memory/core.py" recall "{specific_area}" --limit 3` for focused queries.

**If recall returns empty:** omit all three blocks. No degradation.
**Fast path:** Skip RECALL for single-file changes.

### EXPLORE

**Goal:** Map codebase landscape for this objective, leveraging the recalled insights.
**Exit when:** You have partitioned findings covering files relevant to the objective.

**Greenfield fast path:** If `git ls-files | wc -l` returns 0 or only config files, skip to PLAN with `EXPLORATION: {}`.

**Standard path:**
1. `git ls-files | head -80` — identify 3-6 natural partitions.
2. Spawn explorer swarm: `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. Prompt: `CONTEXT:{relevant_insights}\nSCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: {objective}`. **All explorers in ONE message — no `run_in_background`.**
3. Merge findings by file path. Proceed with successful explorers on crash/error.

### PLAN

**Goal:** Decompose objective into executable task DAG.
**Exit when:** Tasks are created with valid dependencies and no cycles.

1. Spawn planner: `subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt: `OBJECTIVE: {objective}\nEXPLORATION: {findings_json}\nCONSTRAINTS: {constraints_from_recall}\nRISK_AREAS: {risk_areas_from_recall}`. Omit empty blocks. Tactical insights auto-injected via hook.

2. Parse PLAN_SPEC JSON array from result.

3. Create tasks: `TaskCreate(subject="{seq}: {slug}", description=..., activeForm="Building {slug}", metadata={"seq": "{seq}", "relevant_files": [...]})`. Track `seq_to_id[spec.seq] = task_id`.

4. Set dependencies: `TaskUpdate(taskId=seq_to_id[spec.seq], addBlockedBy=[seq_to_id[b], ...])`.

5. Validate: `python3 "$HELIX/lib/build_loop.py" detect-cycles --dependencies '$DEPS_JSON'`. Confirm relevant_files reference paths from exploration.

If PLAN_SPEC empty or ERROR — add exploration context, re-run planner.

### BUILD

**Goal:** Execute all tasks, collect outcomes.
**Exit when:** No pending tasks remain.

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

First, recall insights about the blocked area (graph expansion discovers related insights that might explain the blockage):
```bash
python3 "$HELIX/lib/memory/core.py" recall "{blocked_task_description}" --limit 5 --graph-hops 1
```

Then analyze:
- **One task, obvious workaround:** SKIP (TaskUpdate completed + metadata={helix_outcome: "skipped"}) and store failure insight.
- **Blocked subtree, fixable scope:** Re-plan just the blocked task and dependents. Wire replacement tasks to same predecessors. Don't replan entire DAG.
- **Verify was unclear/wrong:** REPLAN with tighter verification.
- **3+ attempts on same blocker:** ABORT and escalate to user.

### LEARN

**Not optional.** You see cross-task patterns builders cannot. Three steps: observe, ask, store.
**Exit when:** At least one insight stored (or user explicitly dismisses).

#### Step 1: Observe

Review all outcomes internally. Note: which tasks blocked and why, retry patterns, ordering issues, what the user might know. Formulate hypotheses. **Do not store yet.**

#### Step 2: Ask

Present observations to user via `AskUserQuestion`. The user holds domain knowledge inaccessible to the system.

**When to ask:**

| Outcome | Ask? | Rationale |
|---|---|---|
| Fast-path single builder, DELIVERED | No | Trivial |
| Any BLOCKED or PARTIAL | Yes | Highest learning value |
| All DELIVERED (multi-task) | Yes | Approach/ordering insights |

**Question design — options encode hypotheses.** Derive from block reasons, relevant files, task context. User confirms, corrects, or types "Other".

BLOCKED/PARTIAL example:
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
}])
```

All DELIVERED example:
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

- **User selects option or types "Other"**: Combine observation with their answer. Tag `user-provided`.
  ```bash
  python3 "$HELIX/lib/memory/core.py" store \
    --content "When testing OAuth token migration, use mock provider for unit tests because the test OAuth provider rate-limits at 10 req/s and blocks CI" \
    --tags '["user-provided", "testing", "auth"]'
  ```
- **User dismisses**: Fall back to your own cross-task observations. Store without `user-provided` tag.
- **Skipped ask** (fast-path): Store your own observations directly.

Stored insights are automatically linked to semantically related existing insights (similarity >= 0.60). Provenance edges to causal parent insights are recorded during extraction. These relationships improve future recall breadth.

Test: would this help a developer 3 months from now? **Minimum:** one insight per session that completed work.

### COMPLETE

Summarize: tasks delivered, tasks blocked, insights stored (noting which were user-informed). If all tasks blocked, surface the pattern.

---

Agent contracts in `agents/*.md`.
