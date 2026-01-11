---
description: Find decisions that used a pattern.
allowed-tools: Bash, Read, Glob
user-invocable: false
---

# Trace Pattern

Find all decisions that applied a specific pattern.

## Protocol

1. Parse $ARGUMENTS for pattern tag.

2. Trace pattern usage:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/memory.py" trace "$PATTERN"
```

## Output Format

```
Decisions using #pattern/session-token-flow:

  [015] auth-refactor (3d, complete)
  [023] session-timeout (1d, complete)
  [028] token-refresh (0d, active)
```

## Usage

```
/ftl:trace #pattern/session-token-flow
/ftl:trace #constraint/no-jwt-in-cookies
/ftl:trace #decision/use-httponly
```

## Graph Query

This command traverses the `pattern → decisions` edge in the context graph.

```
#pattern/session-token-flow
  └── applied_in → [015, 023, 028]
```

## Constraints

- Read-only
- Returns all decisions, not just recent ones
