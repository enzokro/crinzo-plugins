---
name: helix-query
description: Search helix memory by meaning. Returns relevant insights ranked by relevance × causal effectiveness.
argument-hint: <search text>
---

# Memory Query

```bash
HELIX="$(cat .helix/plugin_root)"

# Semantic search (flat)
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10

# Graph-expanded search (follows relationships)
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --graph-hops 1

# Find related insights to a specific insight
python3 "$HELIX/lib/memory/core.py" neighbors "insight-name" --limit 5
```

Scoring: `rrf_score * (0.5 + 0.5 * causal_adjusted_effectiveness) * recency`.
Graph-expanded results have `_hop: 1` — discovered via relationship edges, not direct match.
Use `--help` for filtering options (`--min-effectiveness`, `--suppress-names`, `--min-relevance`).
