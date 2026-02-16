---
name: helix-query
description: Search helix memory by meaning. Returns relevant insights ranked by relevance × causal effectiveness.
argument-hint: <search text>
---

# Memory Query

Search the learning system for relevant insights using semantic similarity.

## Usage

```
/helix-query authentication patterns
/helix-query "database connection errors"
```

## Execution

```bash
HELIX="$(cat .helix/plugin_root)"
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10
```

## Output

Display each insight with:
- **_score**: Combined ranking (`0.78 * relevance + 0.22 * causal_adjusted_effectiveness`)
- **_relevance**: Cosine similarity to query (0-1)
- **_effectiveness**: Causal-adjusted score (penalizes high-use/low-attribution insights)
- **content**: Full insight text
- **tags**: Category tags

## Filtering

```bash
# Only high-effectiveness insights
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --min-effectiveness 0.3

# Exclude already-seen insights (for diversity)
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --suppress-names '["insight-1", "insight-2"]'
```
