---
description: Show workspace file statistics. Displays counts, sizes, and age metrics for workspace files.
allowed-tools: Bash, Read, Glob
---

# Workspace Statistics

Display quantitative statistics about the workspace.

## Protocol

1. Check if workspace exists:
   ```bash
   ls workspace/ 2>/dev/null || echo "NO_WORKSPACE"
   ```

   If no workspace, report and exit.

2. Gather file counts by status:
   ```bash
   echo "Active: $(ls workspace/*_active* 2>/dev/null | wc -l | tr -d ' ')"
   echo "Blocked: $(ls workspace/*_blocked* 2>/dev/null | wc -l | tr -d ' ')"
   echo "Complete: $(ls workspace/*_complete* 2>/dev/null | wc -l | tr -d ' ')"
   echo "Total: $(ls workspace/*.md 2>/dev/null | wc -l | tr -d ' ')"
   ```

3. Calculate total size:
   ```bash
   du -sh workspace/ 2>/dev/null | cut -f1
   ```

4. Find oldest and newest files:
   ```bash
   ls -t workspace/*.md 2>/dev/null | tail -1  # oldest
   ls -t workspace/*.md 2>/dev/null | head -1  # newest
   ```

5. Get file ages (days since modification):
   ```bash
   for f in workspace/*.md; do
     [ -f "$f" ] && echo "$f: $(( ($(date +%s) - $(stat -f %m "$f")) / 86400 )) days"
   done 2>/dev/null
   ```

## Output Format

```
WORKSPACE STATISTICS

Files:
  Active:   3
  Blocked:  1
  Complete: 12
  Total:    16

Size: 48K

Age:
  Oldest: 001_initial-setup_complete.md (14 days)
  Newest: 016_feature-x_active.md (0 days)
  Average: 5 days

Distribution:
  < 1 day:   2 files
  1-7 days:  8 files
  > 7 days:  6 files
```

## Empty Workspace

If workspace is empty or missing:

```
WORKSPACE STATISTICS

No workspace files found.

Create your first anchor with: /tether:anchor [task description]
```
