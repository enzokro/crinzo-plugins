# Tool Budget Reference

This document defines tool budget rules and exemptions shared across FTL agents.

## Budget Allocation by Agent

| Agent | Base Budget | Notes |
|-------|-------------|-------|
| Explorer | 4 per mode | Fixed, optimized for parallel execution |
| Planner | Unlimited | Reasoning-focused, not tool-heavy |
| Builder | 3-7 (from workspace) | Task-specific, set by Planner |
| Observer | 10 | Analysis + synthesis phases |

## What Counts as a Tool Call

| Action | Counts? | Example |
|--------|---------|---------|
| Read file | YES | `Read {path}` |
| Write/Edit file | YES | `Edit {path}`, `Write {path}` |
| Run command | YES | `Bash {command}` |
| Parse workspace | YES | First action in Builder |
| Read verify_source | YES | Optional test reading |

## Exempt Actions (Don't Count)

| Action | Why Exempt |
|--------|------------|
| Preflight checks | Syntax validation loop (may need multiple attempts) |
| Workspace complete/block | Final state transition |
| Memory operations | Post-task learning |
| Phase transitions | State machine bookkeeping |

## Budget Assignment Rules (Planner)

| Condition | Budget |
|-----------|--------|
| VERIFY task type | 3 |
| Single file, no framework | 3 |
| Multi-file OR framework | 5 |
| Prior failures on similar task | 7 |
| Delta file >100 lines with partial context | +2 bonus |

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
