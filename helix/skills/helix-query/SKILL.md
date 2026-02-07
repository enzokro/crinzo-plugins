---
name: helix-query
description: Search helix memory by meaning. Returns relevant insights ranked by relevance × causal effectiveness × recency.
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
- **name**: Unique identifier (kebab-case slug)
- **content**: Full insight text
- **tags**: Category tags (e.g., debugging, pattern, eval)
- **effectiveness**: 0-1 raw score based on feedback history
- **_effectiveness**: 0-1 causal-adjusted score (penalizes insights with high use but low causal attribution)
- **_relevance**: Cosine similarity to query (0-1)
- **_recency**: Time decay score (0-1)
- **_score**: Combined ranking score

## Scoring Formula

```
score = (0.7 * relevance) + (0.2 * causal_adjusted_effectiveness) + (0.1 * recency)
causal_adjusted_effectiveness = effectiveness * max(0.3, causal_hits / use_count)  # for use_count >= 3
```

Relevance dominates ranking. Effectiveness is penalized when an insight was frequently injected but rarely causally relevant to outcomes (up to 70% penalty).

## Filtering

```bash
# Only return insights with effectiveness > 0.3
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --min-effectiveness 0.3

# Exclude already-seen insights (for diversity)
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --suppress-names '["insight-1", "insight-2"]'
```
