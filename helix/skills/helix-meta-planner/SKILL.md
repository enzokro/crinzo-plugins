---
name: helix-meta-planner
description: Insight-driven planning. Recalls memory, explores informed by insights, decomposes via planner, writes plan.
argument-hint: <objective to plan>
---

# Meta-Planner

Plan-mode-only skill. Produces an implementation plan informed by helix's accumulated project insights.

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

---

## Phases: RECALL → EXPLORE → PLAN → SYNTHESIZE → EXIT

### 1. RECALL

```bash
python3 "$HELIX/lib/injection.py" strategic-recall "$ARGUMENTS"
```

Parse JSON. Use `summary` for triage, synthesize `insights` into blocks:

1. **CONSTRAINTS** — proven insights (`_effectiveness >= 0.70`): decomposition rules, verification needs, sequencing.
2. **RISK_AREAS** — risky insights (`_effectiveness < 0.40`) or `derived`/`failure` tags: flag for extra verification, smaller tasks.
3. **EXPLORATION_TARGETS** — areas referenced by insights that expand scope beyond the naive objective.
4. **GRAPH_DISCOVERED** — `_hop: 1` insights (graph-adjacent, not direct match). Treat as exploration targets.

**Triage signals:** `coverage_ratio > 0.3` = well-mapped, trust constraints. `< 0.1` = uncharted, expand exploration. `graph_expanded_count > 0` = graph surfacing related context.

If recall returns empty -- proceed without constraints; first sessions have no memory.

### 2. EXPLORE

Map areas relevant to both objective and insight-identified targets.

1. `git ls-files | head -80` -- identify 3-6 natural partitions.
2. Select partitions: union of (a) obviously relevant to objective and (b) areas flagged by RECALL insights.
3. Spawn explorer swarm: `subagent_type="helix:helix-explorer"`, `model=sonnet`, `max_turns=30`. **All in ONE message.** Prompt: `SCOPE: {partition}\nFOCUS: {focus}\nOBJECTIVE: $ARGUMENTS`.
4. Merge findings by file path. Proceed with successful explorers on error.

**Obvious scope** (single module, clear file set): skip swarm, use Glob/Grep/Read directly.

### 3. PLAN

Spawn planner: `subagent_type="helix:helix-planner"`, `max_turns=500`. Prompt: `OBJECTIVE: $ARGUMENTS\nEXPLORATION: {merged_findings_json}\nCONSTRAINTS: {constraints_from_recall}\nRISK_AREAS: {risk_areas_from_recall}`. Omit empty blocks. Parse PLAN_SPEC JSON array.

**If decomposition raises questions** -- use `AskUserQuestion` to resolve before synthesis.

### 4. SYNTHESIZE

Write the plan file (path from system context):

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
