---
description: Complete a workspace task.
allowed-tools: Bash, Edit, Read, Glob
---

# Close

## Protocol

Find active file:
```bash
ls .ftl/workspace/*$ARGUMENTS*_active* 2>/dev/null
```

Read file. Fill Delivered section with what was implemented.

Link to git:
```bash
echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo 'none')" >> .ftl/workspace/NNN_slug_complete.md
```

Rename:
```bash
mv .ftl/workspace/NNN_slug_active.md .ftl/workspace/NNN_slug_complete.md
# or _blocked if stuck
```

Report: summary of delivered, final file location.
