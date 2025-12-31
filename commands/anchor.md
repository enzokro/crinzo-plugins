---
description: Create a new workspace anchor file for a task. Establishes Path and Delta before implementation.
allowed-tools: Bash, Write, Read, Glob
---

# Create Anchor

Create a workspace anchor file for the task described in $ARGUMENTS.

## Protocol

1. Query existing workspace:
   ```bash
   ls workspace/ 2>/dev/null | sort -n | tail -5
   ```

   If no workspace folder, create it:
   ```bash
   mkdir -p workspace
   ```

2. Determine:
   - **Next sequence number** (NNN): Highest existing + 1, or 001
   - **Task slug**: Lowercase, hyphenated summary from user input
   - **Lineage**: If building on prior work, note `from-NNN`

3. Create file `workspace/NNN_task-slug_active[_from-NNN].md`:

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## T1
[exploration findings—patterns, constraints, approach]

## Notes
[optional thinking space during build]

## Delivered
[filled by Build at completion]
```

4. Report to user:
   - File created
   - Path and Delta summary
   - Confirm scope before proceeding

## Drift Check

Before creating, verify the request doesn't contain drift signals:
- "flexible," "extensible," "comprehensive"
- "also," "while we're at it"
- "in case," "future-proof"

If detected, ask user to clarify concrete scope first.
