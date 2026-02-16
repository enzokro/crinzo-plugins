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

## Key Metrics

- **status**: `HEALTHY` (has insights + feedback) or `NEEDS_ATTENTION`
- **total_insights**: Count of all insights
- **by_tag**: Breakdown by tags
- **effectiveness**: Average effectiveness of insights with feedback
- **with_feedback**: Insights that have received feedback (use_count > 0)
- **recent_feedback**: Insights with causal feedback in the last hour
- **causal_ratio**: Fraction of feedback events that were causally relevant (healthy > 0.5)
- **issues**: Problems to address
