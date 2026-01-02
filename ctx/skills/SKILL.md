---
name: ctx
description: Surface relevant context from workspace decision traces. Query patterns, check staleness, mark outcomes.
version: 1.0.0
---

# Context Graph

Query workspace patterns. Surface relevant decisions. Track evolution.

## Commands

| Command | Purpose |
|---------|---------|
| `/ctx <topic>` | Surface relevant patterns for topic |
| `/ctx:query <topic>` | Same as above |
| `/ctx:age [days]` | Find stale patterns (default: 30d) |
| `/ctx:signal <+\|-> <pattern>` | Mark pattern outcome |
| `/ctx:mine [workspace]` | Extract and index patterns |

## First Action

Parse $ARGUMENTS:

**No args or topic** — invoke surface agent:
```
Task tool with subagent_type: ctx:surface
```

Pass topic from arguments. Agent searches workspace, ranks by recency and signals.

## Storage

```
.ctx/
├── index.json    # Pattern index with metadata
└── signals.json  # Outcome tracking (+/-)
```

## Pattern Types

| Tag | Meaning |
|-----|---------|
| `#pattern/` | Reusable structural approach |
| `#constraint/` | Hard rule discovered |
| `#decision/` | Choice made with rationale |
| `#antipattern/` | What failed |
| `#connection/` | Cross-domain insight |

## Weighting

```
score = relevance * recency_factor * signal_factor
recency_factor = 1 / (1 + days_old/30)
signal_factor = 1 + (net_signals * 0.2)
```

Recent, positively-signaled patterns rank highest.

## Constraints

- Read-only on workspace files
- Writes only to .ctx/
- No modification to tether
