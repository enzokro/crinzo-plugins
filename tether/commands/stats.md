---
description: Workspace statistics.
allowed-tools: Bash, Read, Glob
---

# Stats

## Protocol

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/wql.py" stat
```

Additional metrics:
```bash
echo "Size:     $(du -sh workspace/ 2>/dev/null | cut -f1)"
echo "Oldest:   $(ls -t workspace/*.md 2>/dev/null | tail -1 | xargs basename 2>/dev/null)"
echo "Newest:   $(ls -t workspace/*.md 2>/dev/null | head -1 | xargs basename 2>/dev/null)"
```
