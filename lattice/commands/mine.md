---
description: Build decision index from workspace files.
allowed-tools: Bash, Read, Glob, Grep, Write
---

# Mine Decisions

Build decision index from workspace files. Extracts full structure.

## Protocol

1. Check workspace exists:
```bash
ls workspace/*.md 2>/dev/null || echo "No workspace"
```

2. Build decision index:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/context_graph.py" mine
```

3. Report indexed decisions and patterns.

## What Gets Indexed

| Field | Source |
|-------|--------|
| Path | `Path:` line in Anchor section |
| Delta | `Delta:` line in Anchor section |
| Traces | `## Thinking Traces` section |
| Delivered | `## Delivered` section |
| Tags | `#pattern/`, `#constraint/`, `#decision/`, etc. |

## Relationships Derived

| Relationship | Source |
|--------------|--------|
| `decision → parent` | `_from-NNN` suffix |
| `pattern → decisions` | Inverse of tags |
| `file → decisions` | Parsed from Delta |

## Output Format

```
Indexed 12 decisions, 8 patterns from workspace
  [001] initial-setup (complete)
  [002] auth-refactor (complete)
  [003] session-handling (complete)
  ...
```

## Storage

```
.lattice/
├── index.json    # Decision records + pattern index
├── edges.json    # Derived relationships
└── signals.json  # Outcome tracking
```

## Constraints

- Only reads workspace files
- Only writes to .lattice/
