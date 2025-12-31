---
description: Create a new workspace anchor file for a task. Establishes Path and Delta before implementation.
allowed-tools: Bash, Write, Read, Glob
---

# Create Anchor

Create a workspace anchor file for the task described in $ARGUMENTS.

## Protocol

1. Ensure workspace exists:
   ```bash
   mkdir -p workspace
   ```

2. Get next sequence number (run this exact command):
   ```bash
   NEXT=$(( $(ls workspace/ 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1 | sed 's/^0*//') + 1 )); printf "%03d\n" $NEXT
   ```

   This outputs a zero-padded 3-digit number (001, 002, ... 999). Use it as `NNN`.

3. Determine:
   - **Task slug**: Lowercase, hyphenated summary from user input
   - **Lineage**: If building on prior work, add `_from-NNN` suffix

4. Create file `workspace/NNN_task-slug_active[_from-NNN].md`:

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Thinking Traces
[exploration findings—patterns, constraints, approach. Build adds here during implementation]

## Delivered
[filled by Build at completion]
```

5. Report to user:
   - File created
   - Path and Delta summary
   - Confirm scope before proceeding

## Drift Check

Before creating, verify the request doesn't contain drift signals:
- "flexible," "extensible," "comprehensive"
- "also," "while we're at it"
- "in case," "future-proof"

If detected, ask user to clarify concrete scope first.
