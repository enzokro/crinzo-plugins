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
