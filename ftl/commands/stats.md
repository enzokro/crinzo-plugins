---
description: Workspace statistics.
allowed-tools: Bash, Read, Glob
---

# Stats

## Protocol

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$TETHER_LIB/wql.py" stat
```

Additional metrics:
```bash
echo "Size:     $(du -sh workspace/ 2>/dev/null | cut -f1)"
echo "Oldest:   $(ls -t workspace/*.md 2>/dev/null | tail -1 | xargs basename 2>/dev/null)"
echo "Newest:   $(ls -t workspace/*.md 2>/dev/null | head -1 | xargs basename 2>/dev/null)"
```
