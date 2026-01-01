---
description: Complete a workspace task.
allowed-tools: Bash, Edit, Read, Glob
---

# Close

## Protocol

Find active file:
```bash
ls workspace/*$ARGUMENTS*_active* 2>/dev/null
```

Read file. Fill Delivered section with what was implemented.

Rename:
```bash
mv workspace/NNN_slug_active.md workspace/NNN_slug_complete.md
# or _blocked if stuck
```

Report: summary of delivered, final file location.
