# Feedback Mechanics

## How Feedback Works

When `feedback(names, outcome)` is called:
- `outcome="delivered"` → effectiveness moves toward 1.0
- `outcome="blocked"` → effectiveness moves toward 0.0
- Uses EMA update: `new_eff = old_eff * 0.9 + outcome_value * 0.1`
- `use_count` increments, `last_used` updates

## CLI

```bash
python3 "$HELIX/lib/memory/core.py" feedback \
    --names '["insight-name-1", "insight-name-2"]' \
    --outcome delivered
```

## Effectiveness Range

| Effectiveness | Interpretation |
|---------------|----------------|
| 0.0 - 0.25 | Consistently unhelpful, candidate for pruning |
| 0.25 - 0.5 | Mixed results or new insight |
| 0.5 | Neutral (default for new insights) |
| 0.5 - 0.75 | Generally helpful |
| 0.75 - 1.0 | Consistently helpful |

## Convergence

With EMA (exponential moving average) at 0.9/0.1:
- 10 consecutive `delivered` → effectiveness ~0.65
- 20 consecutive `delivered` → effectiveness ~0.88
- Mixed results oscillate around 0.5

## When Feedback is Applied

1. Builder completes with `DELIVERED:` or `BLOCKED:` marker
2. SubagentStop hook reads injection-state/{task_id}.json for injected names
3. Hook calls `feedback(names, outcome)` automatically

## Debugging Feedback Issues

If `with_feedback` count doesn't increase:
1. Check injection-state/{task_id}.json exists with `names` array
2. Check task-status.jsonl has matching task_id with valid outcome
3. Verify SubagentStop hook is running (check hooks configuration)
