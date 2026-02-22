---
name: helix-meta-planner
description: Insight-driven planning. Recalls memory, explores informed by insights, decomposes via planner, writes plan.
argument-hint: <objective to plan>
---

# Meta-Planner

Plan-mode-only skill. Produces an implementation plan informed by helix's accumulated project insights. Runs four phases, then presents the plan for approval.

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

---

## Phases: RECALL → EXPLORE → PLAN → SYNTHESIZE → EXIT

### 1. RECALL

Query helix memory for insights relevant to the objective.

```bash
python3 "$HELIX/lib/injection.py" strategic-recall "$ARGUMENTS"
```

Parse the JSON result. Use `summary` for triage, `insights` for synthesis.

From returned insights, synthesize three blocks:

- **CONSTRAINTS** — from proven insights (`_effectiveness >= 0.70`): decomposition patterns, verification requirements, known coupling, sequencing lessons.
- **RISK_AREAS** — from risky insights (`_effectiveness < 0.40`) or `derived`/`failure` tags: areas that historically block, need extra verification or smaller tasks.
- **EXPLORATION_TARGETS** — codebase areas referenced by insight content/tags that need examination even if not obvious from the objective alone. These expand the exploration scope beyond what a naive reading of the objective would suggest.
- **GRAPH_DISCOVERED** — insights with `_hop: 1` (reached via graph relationships, not direct semantic match). These expand exploration partition selection — the graph says "this area is related" even when the query alone wouldn't surface it.

**Graph signal:** `graph_expanded_count > 0` = memory graph is surfacing related context. `graph_expanded_count == 0` with edges in system = query is in an isolated topic cluster.

**Coverage signal:** `coverage_ratio > 0.3` = well-mapped, trust constraints. `coverage_ratio < 0.1` = uncharted, expand exploration.

If recall returns empty — proceed without constraints. First sessions have no memory; that's normal.

### 2. EXPLORE

Map codebase areas relevant to both the objective and insight-identified targets.

1. `git ls-files | head -80` — identify 3-6 natural partitions.
2. Select partitions to explore: the union of (a) partitions obviously relevant to the objective and (b) areas flagged by insights in RECALL. If insights reference specific modules or files, include their containing partitions.
3. Spawn explorer swarm: `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. **All in ONE message.** Prompt each: `SCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: $ARGUMENTS`.
4. Merge findings by file path. Proceed with successful explorers on error.

**If objective scope is obvious** (single module, clear file set): skip the swarm. Use Glob/Grep/Read directly to gather findings. The swarm exists for ambiguous or cross-cutting objectives.

### 3. PLAN

Spawn the planner to decompose into a task DAG.

`subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt:

```
OBJECTIVE: $ARGUMENTS
EXPLORATION: {merged_findings_json}
CONSTRAINTS: {constraints_from_recall}
RISK_AREAS: {risk_areas_from_recall}
```

Omit empty blocks. Parse the PLAN_SPEC JSON array from the result.

**If the planner's decomposition raises questions** — ambiguous requirements, multiple valid approaches, unclear scope boundaries — use `AskUserQuestion` to resolve before proceeding to synthesis.

### 4. SYNTHESIZE

Write the plan file (path provided by system context). Combine all gathered context into a scannable document:

```markdown
# {Objective summary}

## Context
Why this change is needed — the problem, what prompted it, intended outcome.

## Insights Applied
Relevant helix insights and how each shaped the plan:
- [eff%] insight content → influenced {which decision}

## Key Files
Files identified by exploration, grouped by concern:
- {area}: `file1.py`, `file2.py` — {what they do, why they matter}

## Implementation Plan

### 1. {slug} (seq)
{description}
- **Files:** relevant_files
- **Depends on:** blocked_by (or "none — parallel")
- **Verify:** command

### 2. {slug} (seq)
...

## Verification
How to test the complete change end-to-end.
```

**Quality bar:** A developer reading the plan should know exactly what changes, in what order, verified how — without re-exploring the codebase.

### 5. EXIT

Call `ExitPlanMode` to present the plan for user approval.
