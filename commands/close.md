---
description: Complete a workspace task. Fills in the Close section and renames to final status.
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
   - What was the Anchor (original scope and path)?
   - What was actually implemented?
   - What was deliberately omitted?

3. Fill in the Close section:

```markdown
## Close
Omitted: [things not implemented because not requested - be explicit]
Delivered: [exact output - files changed, features added]
Complete: [specific criteria met that prove the anchor is satisfied]
```

4. Determine final status:
   - `_complete`: Work is done, anchor satisfied
   - `_blocked_needs-NNN`: Cannot proceed without another task
   - `_handoff`: Passing to user or another agent

5. Rename file:
   ```bash
   mv workspace/NNN_slug_active.md workspace/NNN_slug_complete.md
   ```

6. Report to user:
   - Summary of what was delivered
   - Summary of what was omitted (this is the discipline evidence)
   - Final file location

## Omissions Principle

The omissions list is the PRIMARY evidence of discipline. "Nothing omitted" is a red flag.

If you cannot name things you deliberately did NOT build, the scope may have been too narrow or you may have over-built.
