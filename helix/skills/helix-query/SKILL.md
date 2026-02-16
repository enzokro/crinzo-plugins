---
name: helix-query
description: Search helix memory by meaning. Returns relevant insights ranked by relevance × causal effectiveness.
argument-hint: <search text>
---

# Memory Query

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10
```

Scoring: `relevance * (0.5 + 0.5 * causal_adjusted_effectiveness)`. Higher `_effectiveness` = more causally validated. Use `--help` for filtering options (`--min-effectiveness`, `--suppress-names`, `--min-relevance`).
