---
name: helix-stats
description: Show learning system health - insight counts, tag distribution, effectiveness, feedback loop status.
---

# System Health

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" health
```

Returns: `status` (HEALTHY/NEEDS_ATTENTION), `total_insights`, `effectiveness`, `with_feedback`, `recent_feedback`, `causal_ratio`, `issues`.
