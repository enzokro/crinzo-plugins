---
description: Create a new workspace anchor file for a task. Establishes scope and plan before implementation.
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
Scope: [one sentence exact requirement from $ARGUMENTS]
Excluded: [what is explicitly not in scope]
Patterns: [existing patterns to follow - search codebase]
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Trace
[Trace reasoning before implementing - every entry connects to Anchor]

## Close
Omitted: [added at completion]
Delivered: [added at completion]
Complete: [added at completion]
```

4. Report to user:
   - File created
   - Anchor summary
   - Confirm scope before proceeding

## Drift Check

Before creating, verify the request doesn't contain drift signals:
- "flexible," "extensible," "comprehensive"
- "also," "while we're at it"
- "in case," "future-proof"

If detected, ask user to clarify concrete scope first.
