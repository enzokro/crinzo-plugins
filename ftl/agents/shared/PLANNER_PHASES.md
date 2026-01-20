---
version: 1.0
---

# Planner Phases

Machine-readable phase definitions for the Planner agent. See [ONTOLOGY.md](ONTOLOGY.md) for term definitions.

## Phase Flow Table

| Phase | Input | Output | Next Phase | Failure Mode |
|-------|-------|--------|------------|--------------|
| READ_EXPLORATION | objective | exploration context | CALCULATE_COMPLEXITY | Fallback to memory.py |
| CALCULATE_COMPLEXITY | exploration | complexity score C | COHERENCE_CHECK | - |
| COHERENCE_CHECK | tasks draft | PROCEED/CONFIRM/CLARIFY | DESIGN_SEQUENCE or STOP | CLARIFY |
| DESIGN_SEQUENCE | coherent tasks | ordered DAG | LOCATE_TARGETS | - |
| LOCATE_TARGETS | delta files | function locations | SET_BUDGETS | - |
| SET_BUDGETS | task complexity | budget per task | EXTRACT_IDIOMS | - |
| EXTRACT_IDIOMS | pattern.idioms | idioms object | OUTPUT_PLAN | - |
| OUTPUT_PLAN | all data | plan.json | DONE | - |

## Phase Details

### READ_EXPLORATION

```
Input: objective text
Output: exploration context dict (from database)

Primary:
  python3 "$(cat .ftl/plugin_root)/lib/exploration.py" read
  # Reads from exploration table in .ftl/ftl.db

Fallback (if missing):
  python3 "$(cat .ftl/plugin_root)/lib/memory.py" context --objective "{objective}" --max-failures 10

Extract:
  - structure.directories, structure.test_pattern
  - pattern.framework, pattern.idioms, pattern.confidence
  - memory.failures, memory.patterns, memory.similar_campaigns
  - delta.candidates

EMIT: "Step: exploration, Status: reading context"
```

### CALCULATE_COMPLEXITY

```
Input: exploration data
Output: complexity score C, task count

Formula:
  C = (sections * 2) + (failure_cost_k / 5) + (framework_level * 3)

Framework Level: Get from registry (canonical source):
  ```bash
  python3 "$(cat .ftl/plugin_root)/lib/framework_registry.py" weight {framework}
  ```
  See `lib/framework_registry.py::FRAMEWORK_PATTERNS` for complexity_weight mappings (0-3).

Task Count: See [planner.md](../planner.md) for canonical formula: `task_count = min(7, max(1, ceil(C / 5)))`

EMIT: "Step: complexity, Status: calculating C={score}"
```

### COHERENCE_CHECK

```
Input: draft task list
Output: PROCEED | CONFIRM | CLARIFY

Question: "Can I write a verify command using only this task's Delta?"

Decision Table:
  | Condition | Decision | Action |
  |-----------|----------|--------|
  | All tasks have clear verify | PROCEED | Continue |
  | Verify needs confirmation | CONFIRM | Ask user |
  | Cannot determine verify | CLARIFY | Stop, output questions |

CLARIFY Triggers:
  - Delta ambiguous (multiple possible files)
  - Test location unknown
  - Multiple implementation approaches
  - Missing dependency information

EMIT: "Step: coherence, Status: {PROCEED|CONFIRM|CLARIFY}"
```

### DESIGN_SEQUENCE

```
Input: coherent tasks
Output: ordered DAG

Task Types:
  1. SPEC: Create tests first, depends on nothing
  2. BUILD: Implement code, depends on prior SPEC/BUILD
  3. VERIFY: Final validation, depends on last BUILD

Parallelization Rules:
  - Independent branches should not depend on each other
  - Convergence tasks depend on multiple branches

Output per task:
  - seq: 3-digit (001, 002, ...)
  - slug: kebab-case
  - type: SPEC | BUILD | VERIFY
  - delta: specific file paths
  - verify: executable command
  - depends: string | string[] | "none"

EMIT: "Step: ordering, Status: {N} tasks, depth={D}"
```

### LOCATE_TARGETS

```
Input: delta files
Output: target_lines for BUILD tasks

Primary: Use exploration.delta.candidates
  candidates = [{path, functions: [{name, line}]}]
  → target_lines = {path: "{min_line-5}-{max_line+15}"}

Fallback:
  grep -n "^def \|^class " {delta_file} | head -20

EMIT: "Step: targets, Status: {function_name}@{line}"
```

### SET_BUDGETS

```
Input: task characteristics
Output: budget per task

Formula:
  MINIMUM = 5                           # READ(1) + IMPLEMENT(1) + VERIFY(1) + RETRY_MARGIN(2)
  FILE_BONUS = max(0, len(delta) - 1)   # Additional files beyond first
  COMPLEXITY = 2 if (prior_failures OR framework_confidence >= 0.6) else 0

  budget = min(9, MINIMUM + FILE_BONUS + COMPLEXITY)

Budget Scenarios:
  | Scenario | Budget | Rationale |
  |----------|--------|-----------|
  | Single file, no complexity | 5 | Minimum viable |
  | Single file + framework | 7 | +2 complexity |
  | 2 files | 6 | +1 file bonus |
  | 3 files + prior failures | 9 | 5 + 2 files + 2 complexity |

Assigned to each task's `budget` field.
```

### EXTRACT_IDIOMS

```
Input: pattern.idioms from exploration
Output: idioms object for plan.json

Structure:
  {
    "required": ["pattern1", "pattern2"],
    "forbidden": ["antipattern1"]
  }

If pattern.confidence < 0.6:
  Include in plan.json but note lower confidence

See [FRAMEWORK_IDIOMS.md](FRAMEWORK_IDIOMS.md) for idiom definitions.
```

### OUTPUT_PLAN

```
Output: plan.json

Required Fields:
  - objective (string)
  - campaign (kebab-slug)
  - framework (string | "none")
  - idioms ({required: [], forbidden: []})
  - tasks (array)

Per-Task Required:
  - seq (3-digit string)
  - slug (kebab-case)
  - delta (string array)
  - verify (string)
  - budget (number)
  - depends (string | string[] | "none")

Optional:
  - type (SPEC | BUILD | VERIFY)
  - preflight (string array)
  - verify_source (string)
  - target_lines (object)
```

## CLARIFY Output Format

When Decision = CLARIFY:

```markdown
## Blocking Questions
1. [Specific question that would unblock planning]

## What I Analyzed (from exploration database)
- Structure: {file_count} files
- Framework: {pattern.framework}
- Delta candidates: {delta.candidates.length} files
- Objective: "{first 50 chars}..."

## Options
- A: [interpretation] → [consequence for task design]
- B: [interpretation] → [consequence for task design]
```

Do not proceed past CLARIFY. Wait for human response.

## Task Graph Visualization

Include in plan output:

```
001 (spec-auth) ──→ 002 (impl-auth) ──┐
                                      ├──→ 005 (integrate)
003 (spec-api) ──→ 004 (impl-api) ───┘
```
