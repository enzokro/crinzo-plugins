---
description: Complete a workspace task. Fills in the Delivered section and renames to final status.
allowed-tools: Bash, Edit, Read, Glob
---

# Close and Complete

Complete the workspace task identified in $ARGUMENTS.

## Protocol

1. Find the active workspace file:
   ```bash
   ls workspace/*$ARGUMENTS*_active* 2>/dev/null
   ```

   If not found, list all active files and ask user to specify.

2. Read the file and analyze:
   - What was the Path (data transformation)?
   - What was the Delta (minimal change)?
   - What was actually implemented?

3. Fill in the Delivered section:

```markdown
## Delivered
[what was implemented—match the Path]
```

4. Determine final status:
   - `_complete`: Work is done
   - `_blocked`: Cannot proceed, documented why

5. Rename file:
   ```bash
   mv workspace/NNN_slug_active.md workspace/NNN_slug_complete.md
   ```

6. Report to user:
   - Summary of what was delivered
   - Final file location
