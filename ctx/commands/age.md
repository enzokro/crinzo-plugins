---
description: Find stale patterns that may need review.
allowed-tools: Bash, Read, Glob
---

# Age Check

Find patterns older than threshold. Stale decisions may no longer apply.

## Protocol

1. Parse $ARGUMENTS for days (default: 30).

2. Query stale patterns:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" age $DAYS
```

3. Report findings with source files.

## Output Format

```
Stale patterns (>30d):
  #pattern/cache-invalidation (45d) from 012_cache-layer_complete.md
  #constraint/max-batch-size (60d) from 005_batch-processing_complete.md
```

## Usage

```
/ctx:age        # Patterns older than 30 days
/ctx:age 14     # Patterns older than 14 days
/ctx:age 90     # Patterns older than 90 days
```

## Constraints

- Read-only
- Reports only, no automatic deprecation
