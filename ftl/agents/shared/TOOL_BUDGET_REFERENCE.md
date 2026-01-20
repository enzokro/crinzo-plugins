---
version: 2.1
---

# Tool Budget Reference

This document defines tool budget rules and exemptions shared across FTL agents.

See [ONTOLOGY.md](ONTOLOGY.md#tool-budget) for canonical terminology:
- `budget`: Total tool calls available
- `budget_used`: Calls consumed
- `budget_remaining`: `budget - budget_used`

## Budget Allocation by Agent

| Agent | Base Budget | Notes |
|-------|-------------|-------|
| Explorer | 4 per mode | Fixed, optimized for parallel execution |
| Planner | Unlimited | Reasoning-focused, not tool-heavy |
| Builder | 5-9 (from workspace) | Task-specific, set by Planner (minimum 5) |
| Observer | 10 | Analysis + synthesis phases |

## What Counts as a Tool Call

| Action | Counts? | Example |
|--------|---------|---------|
| Read file | YES | `Read {path}` |
| Write/Edit file | YES | `Edit {path}`, `Write {path}` |
| Run command | YES | `Bash {command}` |
| Parse workspace | YES | First action in Builder |
| Read verify_source | YES | Optional test reading |

### Tool Call Counting Clarification

Budget counts **tool invocations**, not unique resources:

| Scenario | Tool Calls | Explanation |
|----------|------------|-------------|
| 3 Edit calls to same file | 3 | Each invocation counts |
| 1 Edit call with 3 changes | 1 | Single invocation |
| Read file A, Edit file A | 2 | Two invocations |

**Rationale**: Aligns with API billing model (per-request, not per-resource).

## Exempt Actions (Don't Count)

| Action | Why Exempt |
|--------|------------|
| Preflight checks | Syntax validation loop (may need multiple attempts) |
| Workspace complete/block | Final state transition |
| Memory operations | Post-task learning |
| Phase transitions | State machine bookkeeping |

## Budget Assignment Rules (Planner)

Formula:
```
MINIMUM = 5                           # READ(1) + IMPLEMENT(1) + VERIFY(1) + RETRY_MARGIN(2)
FILE_BONUS = max(0, len(delta) - 1)   # Additional files beyond first
COMPLEXITY = 2 if (prior_failures OR framework_confidence >= 0.6) else 0

budget = min(9, MINIMUM + FILE_BONUS + COMPLEXITY)
```

| Scenario | Budget | Rationale |
|----------|--------|-----------|
| Single file, no complexity | 5 | Minimum viable |
| Single file + framework | 7 | +2 complexity |
| 2 files | 6 | +1 file bonus |
| 3 files + prior failures | 9 | 5 + 2 files + 2 complexity |

## Budget Exhaustion Handling

When budget is exhausted:

1. **Builder**: GOTO BLOCK (budget exhausted)
2. **Observer**: Complete current phase, note incomplete analysis
3. **Explorer**: Return partial results with `status: "partial"`

## Tracking Template

```
Budget: {used}/{total}
Actions:
  1. [action] - Tool count: 1
  2. [action] - Tool count: 2
  ...
```

Emit budget state after each tool call:
```
EMIT: "Budget: {N}/{total}, Action: {description}"
```
