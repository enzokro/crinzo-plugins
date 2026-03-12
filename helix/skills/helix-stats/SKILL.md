---
name: helix-stats
description: Show learning system health - insight counts, tag distribution, effectiveness, feedback loop status.
---

# System Health

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" health
```

Returns: `status` (HEALTHY/NEEDS_ATTENTION), `total_insights`, `total_edges`, `connected_ratio`, `avg_edges_per_insight`, `by_tag`, `effectiveness`, `with_feedback`, `recent_feedback`, `loop_coverage`, `causal_ratio`, `issues`.

## Detailed Stats

For distribution analysis and tuning constant calibration:
```bash
python3 "$HELIX/lib/memory/core.py" stats
```

Returns JSON with:
- `effectiveness` — histogram of insight effectiveness (10 buckets)
- `context_spread` — distribution of generality scores (5 buckets)
- `velocity` — count by recent_uses value
- `top_velocity` — most actively used insights
- `top_connected` — highest graph degree insights
- `session_log` — outcome counts by type and agent
