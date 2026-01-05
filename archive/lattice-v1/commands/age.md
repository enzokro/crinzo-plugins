---
description: Find stale decisions that may need review.
allowed-tools: Bash, Read, Glob
---

# Age Check

Find decisions older than threshold. Stale decisions may no longer apply.

## Protocol

1. Parse $ARGUMENTS for days (default: 30).

2. Query stale decisions:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" age $DAYS
```

3. Report findings with source files and tags.

## Output Format

```
Stale decisions (>30d):

  [012] cache-layer (45d) - #pattern/cache-invalidation
  [005] batch-processing (60d) - #constraint/max-batch-size
```

## Usage

```
/lattice:age        # Decisions older than 30 days
/lattice:age 14     # Decisions older than 14 days
/lattice:age 90     # Decisions older than 90 days
```

## Constraints

- Read-only
- Reports only, no automatic deprecation
