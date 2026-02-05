# CLI Reference

## Memory (6 Core Primitives)

```bash
HELIX="$(cat .helix/plugin_root)"

# Store insight (returns {"status": "added"|"merged", "name": str})
python3 "$HELIX/lib/memory/core.py" store --content "When X, do Y because Z" --tags '["pattern", "typescript"]'

# Recall by semantic similarity (returns list with _relevance, _recency, _score)
python3 "$HELIX/lib/memory/core.py" recall "query text" --limit 5 --min-effectiveness 0.3

# Get specific insight by name
python3 "$HELIX/lib/memory/core.py" get "insight-name"

# Apply feedback after task completion (outcome: delivered|blocked)
python3 "$HELIX/lib/memory/core.py" feedback --names '["insight1", "insight2"]' --outcome delivered

# Decay dormant insights toward neutral (0.5) effectiveness
python3 "$HELIX/lib/memory/core.py" decay --days 30

# Prune consistently unhelpful insights
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Check system health
python3 "$HELIX/lib/memory/core.py" health
```

## Schema (insight table)

| Column | Type | Description |
|--------|------|-------------|
| name | TEXT | Unique slug identifier |
| content | TEXT | Full insight text |
| embedding | BLOB | 384-dim all-MiniLM-L6-v2 vector |
| effectiveness | REAL | 0-1 score, updated via feedback |
| use_count | INT | Times injected and received feedback |
| created_at | TEXT | ISO timestamp |
| last_used | TEXT | ISO timestamp of last feedback |
| tags | TEXT | JSON array of tags |

## Scoring Formula

```
score = (0.5 * relevance) + (0.3 * effectiveness) + (0.2 * recency)
recency = 2^(-days_since_use / 14)
```

## Recall Options

| Option | Description |
|--------|-------------|
| `--limit N` | Maximum results (default 5) |
| `--min-effectiveness F` | Filter below threshold (default 0.0) |

## Feedback Mechanics

- `delivered` → effectiveness moves toward 1.0 (EMA: `eff * 0.9 + 1.0 * 0.1`)
- `blocked` → effectiveness moves toward 0.0 (EMA: `eff * 0.9 + 0.0 * 0.1`)
- `use_count` increments on each feedback call

## Wait Utilities

Zero-context completion polling. **Never use TaskOutput**—use these instead.

```bash
# Wait for parallel builders (polls task-status.jsonl)
python3 "$HELIX/lib/wait.py" wait-for-builders --task-ids "1,2,3" --timeout 180

# Wait for parallel explorers (polls explorer-results/)
python3 "$HELIX/lib/wait.py" wait-for-explorers --count 3 --timeout 120
```

### Agent Output Locations

| Agent | Mode | Output Location |
|-------|------|-----------------|
| builder | background | `.helix/task-status.jsonl` |
| explorer | background | `.helix/explorer-results/{agent_id}.json` |
| planner | foreground | Task returns directly |

## Injection

```bash
# Get insights for a task (writes injection-state/{task_id}.json)
python3 -c "from lib.injection import inject_context; import json; print(json.dumps(inject_context('task objective', 5, 'task_id')))"
```

Returns: `{"insights": ["[75%] When X...", ...], "names": ["insight-name-1", ...]}`

## Verbose Mode

All commands support `--verbose` for structured stderr logging:

```bash
python3 "$HELIX/lib/memory/core.py" --verbose health
```
