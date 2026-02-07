# CLI Reference

## Memory (7 Core Primitives)

```bash
HELIX="$(cat .helix/plugin_root)"

# Store insight (returns {"status": "added"|"merged", "name": str})
python3 "$HELIX/lib/memory/core.py" store --content "When X, do Y because Z" --tags '["pattern", "typescript"]'

# Recall by semantic similarity (returns list with _relevance, _effectiveness, _recency, _score)
python3 "$HELIX/lib/memory/core.py" recall "query text" --limit 5 --min-effectiveness 0.3

# Recall with diversity (exclude already-injected insights)
python3 "$HELIX/lib/memory/core.py" recall "query text" --limit 5 --suppress-names '["insight-1", "insight-2"]'

# Get specific insight by name
python3 "$HELIX/lib/memory/core.py" get "insight-name"

# Apply feedback after task completion (outcome: delivered|blocked|plan_complete)
python3 "$HELIX/lib/memory/core.py" feedback --names '["insight1", "insight2"]' --outcome delivered --causal-names '["insight1"]'

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
| causal_hits | INT | Times causally relevant to outcome |
| created_at | TEXT | ISO timestamp |
| last_used | TEXT | ISO timestamp of last feedback |
| last_feedback_at | TEXT | ISO timestamp of last causal feedback (session-scoped metric) |
| tags | TEXT | JSON array of tags |

## Scoring Formula

```
score = (0.7 * relevance) + (0.2 * causal_adjusted_effectiveness) + (0.1 * recency)
recency = 2^(-days_since_use / 14)
causal_adjusted_effectiveness = effectiveness * max(0.3, causal_hits / use_count)  # for use_count >= 3
```

## Recall Options

| Option | Description |
|--------|-------------|
| `--limit N` | Maximum results (default 5) |
| `--min-effectiveness F` | Filter below raw effectiveness threshold (default 0.0) |
| `--min-relevance F` | Filter below cosine similarity threshold (default 0.35) |
| `--suppress-names JSON` | JSON list of insight names to exclude (for diversity) |

## Feedback Mechanics

- `delivered` / `plan_complete` → effectiveness moves toward 1.0 (EMA: `eff * 0.9 + 1.0 * 0.1`)
- `blocked` → effectiveness moves toward 0.0 (EMA: `eff * 0.9 + 0.0 * 0.1`)
- Causal insights (semantically related to outcome, cosine >= 0.40): full EMA update + `causal_hits` increment
- Non-causal insights: 10% erosion toward neutral (`eff + (0.5 - eff) * 0.10`)
- `use_count` increments on each feedback call; `last_feedback_at` set on causal updates

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
# Batch inject for a wave (diversity + injection-state audit trail — single invocation required)
python3 -c "from lib.injection import batch_inject, reset_session_tracking; import json; reset_session_tracking(); print(json.dumps(batch_inject(['obj1', 'obj2'], 5, task_ids=['task-001', 'task-002'])))"
# Returns: {"results": [{"insights": [...], "names": [...]}, ...], "total_unique": N}
# Side effect: writes injection-state/{task_id}.json per task

# Single-task inject (fallback for one ready task)
python3 -c "from lib.injection import inject_context; import json; print(json.dumps(inject_context('task objective', 5, 'task_id')))"
# Returns: {"insights": ["[72%] When X...", ...], "names": ["insight-name-1", ...]}
```

Percentages in insights reflect causal-adjusted effectiveness, not raw.

## Verbose Mode

All commands support `--verbose` for structured stderr logging:

```bash
python3 "$HELIX/lib/memory/core.py" --verbose health
```
