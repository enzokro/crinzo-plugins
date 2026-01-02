---
description: Find decisions that affected a file.
allowed-tools: Bash, Read, Glob
---

# File Impact

Find decisions that touched a file pattern.

## Protocol

1. Parse $ARGUMENTS for file pattern.

2. Query file impact:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" impact "$FILE"
```

## Output Format

```
Decisions affecting 'auth':

  [015] auth-refactor (3d)
    Delta: src/auth/*.ts

  [008] security-audit (12d)
    Delta: src/**/*.ts
```

## Usage

```
/ctx:impact auth           # Files containing "auth"
/ctx:impact src/api        # Files in src/api/
/ctx:impact session.ts     # Specific file
```

## Graph Query

This command traverses the `file → decisions` edge in the context graph.

```
src/auth/*.ts
  └── modified_by → [015, 023]
```

## Constraints

- Read-only
- Matches file patterns from Delta fields
