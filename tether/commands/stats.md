---
description: Workspace statistics.
allowed-tools: Bash, Read, Glob
---

# Stats

## Protocol

```bash
ls workspace/ 2>/dev/null || echo "No workspace"
```

```bash
echo "Active:   $(ls workspace/*_active* 2>/dev/null | wc -l | tr -d ' ')"
echo "Blocked:  $(ls workspace/*_blocked* 2>/dev/null | wc -l | tr -d ' ')"
echo "Complete: $(ls workspace/*_complete* 2>/dev/null | wc -l | tr -d ' ')"
echo "Total:    $(ls workspace/*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "Size:     $(du -sh workspace/ 2>/dev/null | cut -f1)"
```

Oldest/newest:
```bash
ls -t workspace/*.md 2>/dev/null | tail -1  # oldest
ls -t workspace/*.md 2>/dev/null | head -1  # newest
```
