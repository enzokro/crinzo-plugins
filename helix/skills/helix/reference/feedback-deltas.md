# Feedback Mechanics

## How Feedback Works

When `feedback(names, outcome, causal_names)` is called:
- `outcome="delivered"` or `"plan_complete"` → effectiveness moves toward 1.0
- `outcome="blocked"` → effectiveness moves toward 0.0
- **Causal insights** (semantically related to outcome): EMA update `new_eff = old_eff * 0.9 + outcome_value * 0.1`, `causal_hits` increments, `last_feedback_at` set
- **Non-causal insights**: 4% erosion toward neutral `new_eff = old_eff + (0.5 - old_eff) * 0.04`
- `use_count` increments for all, `last_used` updates

## CLI

```bash
python3 "$HELIX/lib/memory/core.py" feedback \
    --names '["insight-name-1", "insight-name-2"]' \
    --outcome delivered \
    --causal-names '["insight-name-1"]'
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

1. Builder or planner completes with `DELIVERED:`/`BLOCKED:`/`PLAN_COMPLETE:` marker
2. SubagentStop hook reads injection-state/{task_id}.json for injected names
3. Hook filters injected names to those causally relevant (cosine similarity >= 0.25 with outcome text)
4. Hook calls `feedback(names, outcome, causal_names)` automatically

## Debugging Feedback Issues

If `recent_feedback` is 0 after a session with builds:
1. Check injection-state/{task_id}.json exists with `names` array
2. Check task-status.jsonl has matching task_id with valid outcome
3. Verify SubagentStop hook is running (check hooks configuration)
4. Check `causal_ratio` in health output — low ratio means insights aren't matching outcomes semantically
