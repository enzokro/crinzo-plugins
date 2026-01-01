---
description: Create workspace anchor file manually.
allowed-tools: Bash, Write, Read, Glob
---

# Create Anchor

## Protocol

```bash
mkdir -p workspace
NEXT=$(( $(ls workspace/ 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1 | sed 's/^0*//') + 1 )); printf "%03d\n" $NEXT
```

Create `workspace/NNN_task-slug_active[_from-NNN].md`:

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change]

## Thinking Traces
[exploration findings]

## Delivered
[filled by Build]
```

## Drift Check

Before creating, reject if request contains:
- "flexible," "extensible," "comprehensive"
- "also," "while we're at it"
- "in case," "future-proof"

Clarify concrete scope first.
