---
name: helix-stats
description: Show learning system health - memory counts, edges, effectiveness, feedback loop status.
---

# System Health

Display memory system statistics, graph edges, and learning loop status.

## Execution

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
python3 "$HELIX/lib/memory/core.py" health
```

## Output Includes

- **total_memories**: Count of all memories
- **total_edges**: Count of graph relationships
- **by_type**: Breakdown by failure/pattern/systemic
- **edge_types**: Breakdown by solves/co_occurs/similar/causes
- **effectiveness**: Overall helped/(helped+failed) ratio
- **with_feedback**: Memories that have received feedback
- **status**: HEALTHY or NEEDS_ATTENTION
- **issues**: List of problems if any

## Maintenance Commands

After viewing health, consider running maintenance:

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Decay dormant memories (halve scores for unused memories)
python3 "$HELIX/lib/memory/core.py" decay --days 30 --min-uses 2

# Prune ineffective memories (remove low performers)
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Consolidate similar memories (merge near-duplicates)
python3 "$HELIX/lib/memory/core.py" consolidate
```

## Edge Management

Query and create edges:

```bash
# View all edges for a memory
python3 "$HELIX/lib/memory/core.py" edges --name "memory-name"

# View edges by type
python3 "$HELIX/lib/memory/core.py" edges --rel solves

# Create an edge (pattern solves failure)
python3 "$HELIX/lib/memory/core.py" edge --from "pattern-name" --to "failure-name" --rel solves

# Get edge suggestions for a memory (code-assisted)
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
```

## Systemic Detection

Find similar recent failures (for escalation decisions):

```bash
# Check for recurring failure patterns
python3 "$HELIX/lib/memory/core.py" similar-recent "failure trigger" --threshold 0.7 --days 7

# Filter by type
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --type failure --days 14
```

If count >= 2, consider escalating to systemic type.

## Verbose Mode

All commands support `--verbose` for structured stderr logging:

```bash
python3 "$HELIX/lib/memory/core.py" --verbose health
```
