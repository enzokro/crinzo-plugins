---
name: ctx
description: Context graph for workspace decisions. Query precedents, trace patterns, check staleness.
version: 2.0.0
---

# Context Graph

Decisions are primary. Patterns are edges. Precedent becomes searchable.

## Commands

| Command | Purpose |
|---------|---------|
| `/ctx <topic>` | Surface relevant decisions for topic |
| `/ctx:query <topic>` | Same as above |
| `/ctx:decision NNN` | Full decision record with traces |
| `/ctx:lineage NNN` | Decision ancestry chain |
| `/ctx:trace <pattern>` | Find decisions using a pattern |
| `/ctx:impact <file>` | Find decisions affecting a file |
| `/ctx:age [days]` | Find stale decisions (default: 30d) |
| `/ctx:signal <+\|-> <pattern>` | Mark pattern outcome |
| `/ctx:mine` | Build decision index from workspace |

## First Action

Parse $ARGUMENTS:

**Topic query** — invoke surface agent:
```
Task tool with subagent_type: ctx:surface
```

Pass topic from arguments. Agent searches workspace, ranks by recency and signals.

## Data Model

```
.ctx/
├── index.json    # Decision records + pattern index
├── edges.json    # Derived relationships
└── signals.json  # Outcome tracking (+/-)
```

## Decision Record

```json
{
  "015": {
    "file": "015_auth-refactor_complete.md",
    "slug": "auth-refactor",
    "status": "complete",
    "parent": "008",
    "path": "User credentials → validation → session token",
    "delta": "src/auth/*.ts",
    "traces": "Chose token refresh over re-auth...",
    "delivered": "Modified session.ts...",
    "tags": ["#pattern/session-token-flow"]
  }
}
```

## Graph Edges

| Edge | Query |
|------|-------|
| `decision → parent` | `/ctx:lineage NNN` |
| `pattern → decisions` | `/ctx:trace #pattern/name` |
| `file → decisions` | `/ctx:impact src/auth` |

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
