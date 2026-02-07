---
name: helix-stats
description: Show learning system health - insight counts, tag distribution, effectiveness, feedback loop status.
---

# System Health

Display memory system statistics and learning loop status.

## Execution

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" health
```

## Output Includes

- **status**: `HEALTHY` or `NEEDS_ATTENTION`
- **total_insights**: Count of all insights
- **by_tag**: Breakdown by tags (debugging, pattern, eval, etc.)
- **effectiveness**: Average effectiveness of insights with feedback
- **with_feedback**: Count of insights that have received feedback (use_count > 0)
- **recent_feedback**: Count of insights that received causal feedback in the last hour (session-scoped signal)
- **causal_ratio**: Fraction of feedback events that were causally relevant
- **issues**: List of problems if any

## Example Output

```json
{
  "status": "HEALTHY",
  "total_insights": 30,
  "by_tag": {"debugging": 6, "pattern": 10, "eval": 5, ...},
  "effectiveness": 0.65,
  "with_feedback": 12,
  "recent_feedback": 3,
  "causal_ratio": 0.82,
  "issues": []
}
```

## Interpreting Results

| Metric | Healthy | Action if Unhealthy |
|--------|---------|---------------------|
| total_insights | > 0 | Run helix to build memories |
| with_feedback | > 0 | Ensure feedback() called after builds |
| recent_feedback | > 0 (after a build session) | Check injection-state files and SubagentStop hook |
| causal_ratio | > 0.5 | Insights aren't matching outcomes; review content quality |
| effectiveness | > 0.5 | Prune low performers |
| issues | empty | Address listed issues |

## Maintenance Commands

```bash
HELIX="$(cat .helix/plugin_root)"

# Decay dormant insights toward neutral (0.5) effectiveness
python3 "$HELIX/lib/memory/core.py" decay --days 30

# Prune insights that consistently fail (effectiveness < 0.25 with 3+ uses)
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3
```

## Feedback Mechanics

When `feedback(names, outcome, causal_names)` is called:
- `outcome="delivered"` or `"plan_complete"` → effectiveness moves toward 1.0
- `outcome="blocked"` → effectiveness moves toward 0.0
- Causal insights: EMA update `new_eff = old_eff * 0.9 + outcome_value * 0.1`
- Non-causal insights: 10% erosion toward neutral `new_eff = old_eff + (0.5 - old_eff) * 0.10`
- `use_count` increments, `last_used` updates, `last_feedback_at` set on causal

## Database Location

```bash
# Default location
.helix/helix.db

# Inspect directly
sqlite3 .helix/helix.db "SELECT name, effectiveness, use_count FROM insight ORDER BY effectiveness DESC LIMIT 10"
```
