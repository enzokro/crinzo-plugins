# CLI Reference

## Schema (insight table)

| Column | Type | Description |
|--------|------|-------------|
| name | TEXT | Unique slug identifier |
| content | TEXT | Full insight text |
| embedding | BLOB | 256-dim snowflake-arctic-embed-m-v1.5 vector |
| effectiveness | REAL | 0-1 score, EMA-updated via feedback |
| use_count | INT | Times injected and received feedback |
| causal_hits | INT | Times causally relevant to outcome |
| created_at | TEXT | ISO timestamp |
| last_used | TEXT | ISO timestamp of last feedback |
| last_feedback_at | TEXT | ISO timestamp of last causal feedback |
| tags | TEXT | JSON array of tags |

## Recall Options

| Option | Description |
|--------|-------------|
| `--limit N` | Maximum results (default 5) |
| `--min-effectiveness F` | Filter below raw effectiveness threshold (default 0.0) |
| `--min-relevance F` | Filter below cosine similarity threshold (default 0.35) |
| `--suppress-names JSON` | JSON list of insight names to exclude (for diversity) |

## Get Command

```bash
# Retrieve specific insight by name (returns full record with all fields)
python3 "$HELIX/lib/memory/core.py" get "insight-name"
```

## Verbose Mode

All memory commands support `--verbose` for structured stderr logging.
