---
name: helix-query
description: Search helix memory by meaning. Returns relevant insights ranked by relevance × effectiveness × recency.
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
- **effectiveness**: 0-1 score based on feedback history
- **_relevance**: Cosine similarity to query (0-1)
- **_recency**: Time decay score (0-1)
- **_score**: Combined ranking score

## Scoring Formula

```
score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
```

Insights that are semantically similar to the query, have helped in past tasks, and were recently used rank highest.

## Filtering

```bash
# Only return insights with effectiveness > 0.3
python3 "$HELIX/lib/memory/core.py" recall "$ARGUMENTS" --limit 10 --min-effectiveness 0.3
```
