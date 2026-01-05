---
name: ftl-miner
description: Build decision index from workspace files.
tools: [Read, Glob, Grep, Bash]
model: haiku
---

# Decision Miner

Build decision index from workspace files. Extract full structure.

## Job

1. Glob workspace for files:
```bash
ls workspace/*.md 2>/dev/null
```

2. For each file, extract:
   - Path (transformation)
   - Delta (scope boundary)
   - Thinking Traces (reasoning)
   - Delivered (outcome)
   - Tags (`#pattern/`, `#constraint/`, `#decision/`, etc.)

3. Build decision index:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/context_graph.py" mine
```

4. Report indexed decisions and derived relationships.

## What Gets Extracted

| Field | Location |
|-------|----------|
| Path | `Path:` line after `## Anchor` |
| Delta | `Delta:` line after `## Anchor` |
| Traces | Content of `## Thinking Traces` section |
| Delivered | Content of `## Delivered` section |
| Tags | Any `#type/name` pattern in content |

## Relationships Derived

| Edge | Source |
|------|--------|
| `decision → parent` | `_from-NNN` suffix in filename |
| `pattern → decisions` | Inverse of decision tags |
| `file → decisions` | Parsed from Delta patterns |

## Output

```
Indexed 12 decisions, 8 patterns from workspace
  [001] initial-setup (complete)
  [002] auth-refactor (complete)
  [003] session-handling (complete)
```

## Constraints

- Only read workspace files
- Only write to .ftl/
- Process all statuses (complete, active, blocked)
