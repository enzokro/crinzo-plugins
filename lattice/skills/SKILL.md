---
name: lattice
description: Context graph for workspace decisions. Query precedents, trace patterns, check staleness.
version: 2.0.0
---

## Output Style: Ranked Memory

Order communicates relevance. Numbers attribute. Signals quantify.

| Principle | Expression |
|-----------|------------|
| **Position is ranking** | First result is most relevant; order matters |
| **Attribution is mandatory** | Every fact traces to `[NNN]` |
| **Signals not opinions** | `(net +3)` not "this worked well" |
| **Quote, don't paraphrase** | Excerpt Thinking Traces with quotation marks |
| **Absence is information** | "No decisions match" is valid, useful output |

Apply these principles to all lattice work.

---

# Context Graph

Decisions are primary. Patterns are edges. Precedent becomes searchable.

## Commands

| Command                            | Purpose                              |
| ---------------------------------- | ------------------------------------ |
| `/lattice <topic>`                 | Surface relevant decisions for topic |
| `/lattice:query <topic>`           | Same as above                        |
| `/lattice:decision NNN`            | Full decision record with traces     |
| `/lattice:lineage NNN`             | Decision ancestry chain              |
| `/lattice:trace <pattern>`         | Find decisions using a pattern       |
| `/lattice:impact <file>`           | Find decisions affecting a file      |
| `/lattice:age [days]`              | Find stale decisions (default: 30d)  |
| `/lattice:signal <+\|-> <pattern>` | Mark pattern outcome                 |
| `/lattice:mine`                    | Build decision index from workspace  |

## First Action

Parse $ARGUMENTS:

**Topic query** — invoke surface agent:
```
Task tool with subagent_type: lattice:surface
```

Pass topic from arguments. Agent searches workspace, ranks by recency and signals.

## Data Model

```
.lattice/
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

| Edge                  | Query                          |
| --------------------- | ------------------------------ |
| `decision → parent`   | `/lattice:lineage NNN`         |
| `pattern → decisions` | `/lattice:trace #pattern/name` |
| `file → decisions`    | `/lattice:impact src/auth`     |

## Weighting

```
score = relevance * recency_factor * signal_factor
recency_factor = 1 / (1 + days_old/30)
signal_factor = 1 + (net_signals * 0.2)
```

Recent, positively-signaled patterns rank highest.

## Constraints

- Read-only on workspace files
- Writes only to .lattice/
- No modification to tether
