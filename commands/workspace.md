---
description: Query the cognitive workspace. Shows active tasks, lineage, and available context.
allowed-tools: Bash, Read, Glob
---

# Workspace Query

Query the cognitive workspace for this project.

## Protocol

1. List workspace contents:
   ```bash
   ls -la workspace/ 2>/dev/null || echo "No workspace folder found"
   ```

2. If filter provided in $ARGUMENTS:
   - "active" → show only `*_active*` files
   - "blocked" → show only `*_blocked*` files
   - "complete" → show only `*_complete*` files
   - A number → show files with that sequence or lineage

3. Report to user:
   - **Active work**: Tasks currently in progress
   - **Blocked items**: What they need
   - **Lineage structure**: How understanding connects
   - **Next sequence**: What NNN to use for new work
   - **Available context**: What prior understanding exists

4. If no workspace folder exists:
   - Report this to user
   - Suggest creating first anchor with `/tether:anchor [task]`

## Output Format

```
WORKSPACE STATUS

Active:
  - 003_feature-x_active (from 001)

Blocked:
  - 002_api-auth_blocked_needs-001

Complete:
  - 001_initial-setup_complete

Next sequence: 004

Lineage:
  001 → 002 (blocked)
      → 003 (active)
```
