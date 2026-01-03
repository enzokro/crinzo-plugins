---
name: forge
description: Meta-orchestrator for compound development. Campaigns over tasks.
version: 1.0.0
---

# Forge

Campaigns. Precedent. Synthesis. Growth.

## First Action

Invoke orchestrator:
```
Task tool with subagent_type: forge:forge-orchestrator
```

Pass campaign objective or "resume" for continuation.

## Flow

```
forge:planner → task breakdown
  ↓
lattice:surface → precedent query (before each task)
  ↓
tether:tether-orchestrator → task execution (loop)
  ↓
lattice:signal → feedback (after patterns emerge)
  ↓
forge:synthesizer → meta-learning (on campaign complete)
```

## Commands

| Command | Purpose |
|---------|---------|
| `/forge <objective>` | Start or resume campaign |
| `/forge:status` | Campaign + active workspace status |
| `/forge:learn` | Force synthesis manually |

## Constraints

| Constraint | Meaning |
|------------|---------|
| Delegate over implement | Tether does all work |
| Precedent over discovery | Check lattice first |
| Coordinate over block | Report conflicts, human decides |
| Campaign over sprint | Bounded objectives |

## State

```
.forge/
├── campaigns/
│   ├── active/      # Current campaigns
│   └── complete/    # Finished campaigns
└── synthesis.json   # Meta-patterns
```

Coordination via tether's `workspace/*_active*.md` files.

## Integration

### Tether
```
Task tool with subagent_type: tether:tether-orchestrator
```
Inject precedent context. Capture patterns. Update campaign.

### Lattice
```bash
python3 ../lattice/lib/context_graph.py query "$TOPIC"
python3 ../lattice/lib/context_graph.py signal + "#pattern/name"
```
Query before work. Signal after.

## Campaign

Not project (too permanent). Not task (too granular). A campaign has:
- Clear objective
- Multiple tether tasks
- Bounded scope
- Success criteria

## Why Forge

Ralph Wiggum re-injected prompts. No memory. No learning. No coordination.

Forge:
- Remembers through lattice
- Learns through synthesis
- Compounds through campaigns

Each campaign leaves the system smarter.
