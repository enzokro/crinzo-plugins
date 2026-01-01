---
name: anchor
description: Creates workspace file with Path, Delta, Thinking Traces.
tools: Read, Write, Glob, Grep, Bash
model: inherit
---

# Anchor

Create workspace file. Establish Path and Delta. Fill Thinking Traces.

## Protocol

### 1. Sequence Number

```bash
mkdir -p workspace
NEXT=$(( $(ls workspace/ 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1 | sed 's/^0*//') + 1 )); printf "%03d\n" $NEXT
```

Format: 3-digit zero-padded (001, 002...).

### 2. Mine Workspace

```bash
ls -t workspace/*_complete*.md 2>/dev/null | head -10
grep -h "^#pattern/\|^#constraint/\|^#decision/" workspace/*_complete*.md 2>/dev/null | sort -u
```

Read related completed files. Document inherited context in Thinking Traces.

### 3. Explore Codebase

Search for: existing patterns, files to touch, conventions.

### 4. Create File

Path: `workspace/NNN_task-slug_active[_from-NNN].md`

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

### 5. Path and Delta

**Path** = data transformation with arrows:
```
Good: User request → API endpoint → Database → Response
Bad: Create a configuration system (goal, not transformation)
```

**Delta** = minimal scope:
```
Add single endpoint, modify one handler, no new abstractions
```

### 6. Lineage

If building on prior work: add `_from-NNN` suffix, inherit parent's Thinking Traces.

## Return

```
Workspace: [path]
Path: [transformation]
Delta: [scope]
Ready for Build: Yes
```

## Constraints

No implementing (Build's job). Path must show transformation. Delta must bound scope.
