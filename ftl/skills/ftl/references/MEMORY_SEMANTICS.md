# FTL Memory Semantics

FTL uses semantic embeddings (sentence-transformers) for intelligent memory operations.

## Operations

| Operation | Behavior |
|-----------|----------|
| **Retrieval** | `--objective` scores memories by cosine similarity, returns most relevant |
| **Deduplication** | 85% semantic similarity threshold prevents near-duplicate entries |
| **Query** | `/ftl query "topic"` ranks results by semantic relevance |
| **Relationships** | Graph edges between related failures enable multi-hop discovery |

## Scoring

**Hybrid Score**: `score = relevance * log2(cost + 1)`
- Balances semantic relevance with failure cost/pattern value

**Importance**: `importance = log2(value + 1) * age_decay * access_boost * effectiveness`
- `access_boost`: `1 + 0.1 * access_count`
- `effectiveness`: `0.5 + (times_helped / total_feedback)` (maps to 0.5-1.5)

## Decay

**Age Decay**: Exponential decay with 30-day half-life
- `decay_factor = 0.5^(age_days / 30)`
- Newer entries have higher importance
- Frequently accessed entries resist decay via access_boost

## Feedback Loop

**Effectiveness Tracking**:
- `times_helped`: Incremented when memory contributed to task success
- `times_failed`: Incremented when injected memory didn't help
- Ratio affects importance: helpful memories persist (1.5x), unhelpful decay (0.5x)

**Builder reports via `--utilized`**:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py complete PATH \
  --delivered "..." \
  --utilized '[{"name": "pattern-name", "type": "pattern"}]'
```

## Graph Traversal

**BFS Discovery**: `get_related_entries()` with configurable hop depth (default: 2)
- Related entries discovered via bidirectional edges
- Enables multi-hop pattern matching across failures

## Similar Campaigns

**Transfer Learning**: `/ftl similar` finds past campaigns with matching objectives
- Uses objective embedding similarity (60% weight)
- Delta file overlap (30% weight)
- Task count similarity (10% weight)

## Fallback

If sentence-transformers unavailable, falls back to SequenceMatcher string similarity.
