---
name: anchor
description: Creates workspace file with Path, Delta, Thinking Traces.
tools: Read, Write, Glob, Grep, Bash
model: inherit
---

# Anchor

Create workspace file. Establish Path, Delta, and Verify. Fill Thinking Traces.

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
Delta: [file paths or patterns]
Verify: [verification command, if discovered]
Branch: [current branch if not main]

## Thinking Traces
[exploration findings]

## Delivered
[filled by Build]
```

### 4b. Discover Verification

Inherit from campaign task if available (planner already discovered).

Otherwise detect:
```bash
# Test file co-location
ls ${DELTA_DIR}/*.test.* ${DELTA_DIR}/*.spec.* 2>/dev/null

# Project test scripts
grep -E '"test"|"typecheck"' package.json 2>/dev/null

# Makefile targets
grep -E '^test:|^check:' Makefile 2>/dev/null
```

If found, add to Anchor. If not, leave Verify field empty (graceful skip).

Get branch:
```bash
git branch --show-current 2>/dev/null
```

### 5. Path, Delta, Verify

**Path** = data transformation with arrows:
```
Good: User request → API endpoint → Database → Response
Bad: Create a configuration system (goal, not transformation)
```

**Delta** = minimal scope with file precision:
```
Vague: modify auth handling (hook can't enforce)
Precise: src/auth/*.ts, tests/auth/*.test.ts (hook enforces)
```

**Verify** = verification command relevant Delta changes:
```
Good: uv run python -m pytest tests/auth/*.test.py
Bad: python tests/auth/*.test.py
```

### 6. Lineage

If building on prior work: add `_from-NNN` suffix, inherit parent's Thinking Traces.

## Return

```
Workspace: [path]
Path: [transformation]
Delta: [scope]
Verify: [command or "none discovered"]
Ready for Build: Yes
```

## Constraints

No implementing (Build's job). Path must show transformation. Delta must bound scope.
