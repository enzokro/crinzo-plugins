---
name: helix-stats
description: Show learning system health - memory counts, effectiveness, feedback loop status.
---

# System Health

Display memory system statistics and learning loop status.

## Execution

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
python3 "$HELIX/lib/memory/core.py" health
```

## After Display

Consider running maintenance:
```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
python3 "$HELIX/lib/memory/core.py" consolidate  # Merge similar memories
python3 "$HELIX/lib/memory/core.py" decay        # Identify dormant memories
python3 "$HELIX/lib/memory/core.py" prune        # Remove ineffective memories
```
