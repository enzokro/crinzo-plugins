---
name: helix-query
description: Search helix memory by meaning. Returns relevant failures and patterns.
argument-hint: <search text>
---

# Memory Query

Search the learning system for relevant memories with graph expansion.

## Usage

```
/helix-query authentication patterns
/helix-query "database connection errors"
```

## Execution

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --expand
```

The `--expand` flag includes 1-hop graph neighbors, surfacing:
- Solutions that solved similar failures (via `solves` edges)
- Related patterns (via `similar` edges)
- Co-occurring issues (via `co_occurs` edges)

## Output

Display each memory with:
- Name and type (failure/pattern/systemic)
- Trigger and resolution
- Effectiveness score
- Relevance to query
- Whether discovered via edge (`_via_edge: true`)
