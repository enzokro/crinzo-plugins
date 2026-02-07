# Feedback Mechanics

## Effectiveness Range

| Effectiveness | Interpretation |
|---------------|----------------|
| 0.0 - 0.25 | Consistently unhelpful, candidate for pruning |
| 0.25 - 0.5 | Mixed results or new insight |
| 0.5 | Neutral (default) |
| 0.5 - 0.75 | Generally helpful |
| 0.75 - 1.0 | Consistently helpful |

## Convergence Math

EMA at 0.9/0.1: 10 consecutive `delivered` → ~0.65; 20 → ~0.88; mixed oscillates around 0.5.

Non-causal erosion (10%): from 0.75, after 11 steps → ~0.578. Converges toward 0.5, never crosses.

Causal-adjusted at read time: `eff * max(0.3, causal_hits / use_count)` for `use_count >= 3`.

## Debugging Checklist

If `recent_feedback` is 0 after a session with builds:
1. Check `injection-state/{task_id}.json` has `names` array
2. Check `task-status.jsonl` has matching task_id with valid outcome
3. Verify SubagentStop hook is running (hooks configuration)
4. Check `causal_ratio` in health — low ratio means insights aren't matching outcomes semantically
