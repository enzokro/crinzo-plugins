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
- **issues**: List of problems if any

## Example Output

```json
{
  "status": "HEALTHY",
  "total_insights": 30,
  "by_tag": {"debugging": 6, "pattern": 10, "eval": 5, ...},
  "effectiveness": 0.65,
  "with_feedback": 12,
  "issues": []
}
```

## Interpreting Results

| Metric | Healthy | Action if Unhealthy |
|--------|---------|---------------------|
| total_insights | > 0 | Run helix to build memories |
| with_feedback | > 0 | Ensure feedback() called after builds |
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

When `feedback(names, outcome)` is called:
- `outcome="delivered"` → effectiveness moves toward 1.0
- `outcome="blocked"` → effectiveness moves toward 0.0
- Uses EMA update: `new_eff = old_eff * 0.9 + outcome * 0.1`
- `use_count` increments, `last_used` updates

## Database Location

```bash
# Default location
.helix/helix.db

# Inspect directly
sqlite3 .helix/helix.db "SELECT name, effectiveness, use_count FROM insight ORDER BY effectiveness DESC LIMIT 10"
```
