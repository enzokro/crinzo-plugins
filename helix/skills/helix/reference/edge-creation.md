# Edge Creation Rules

## Edge Type Decision Table

| Situation | Edge Type | Direction | Weight |
|-----------|-----------|-----------|--------|
| Pattern's resolution explicitly solved a failure | `solves` | pattern -> failure | 1.0 |
| Two memories both helped same task | `co_occurs` | bidirectional | 0.5 each |
| Failure A led to discovering failure B | `causes` | A -> B | 1.0 |
| Memories have similar triggers (I note this) | `similar` | bidirectional | 0.5 each |
| Pattern supersedes older, less effective pattern | `similar` | new -> old | 1.0 |

## When to Create Edges

- **solves**: Builder explicitly avoided a known failure using injected pattern
- **co_occurs**: Multiple injected memories all contributed to success
- **causes**: Debugging one failure revealed another deeper failure
- **similar**: Code suggests high similarity OR I notice conceptual overlap

## Code-Assisted Discovery

After storing a memory, query for suggestions:

```bash
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
```

Returns `[{from, to, rel_type, reason, confidence}]`. Review each suggestion and create edges with judgment:

```bash
python3 "$HELIX/lib/memory/core.py" edge \
    --from "pattern-name" \
    --to "failure-name" \
    --rel solves \
    --weight 1.0
```

Graph expansion surfaces solutions via edges on next recall.

## Edge Weight Mechanics

- Weights accumulate on repeated edge creation (capped at 10.0)
- Temporal sorting prefers recent edges during expansion
- Use `decay-edges` to halve weights on dormant relationships
