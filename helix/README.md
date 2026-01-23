# Helix

Structured orchestrator with integrated memory for Claude Code.

## Overview

```
EXPLORE → PLAN → BUILD → OBSERVE
   │                        │
   │      recall/inject     │
   └────────────────────────┘
         feedback loop
```

- **Explorer**: Gathers context (structure, patterns, memory, targets)
- **Planner**: Decomposes objectives into executable task DAG
- **Builder**: Executes tasks with memory injection and constraints
- **Observer**: Extracts learning from outcomes

## Installation

```bash
pip install sentence-transformers  # For semantic search
```

## Usage

### Full Pipeline

```
/helix implement user authentication with JWT tokens
```

This will:
1. **Explore**: Gather codebase context, query relevant memories
2. **Plan**: Decompose into tasks with dependencies
3. **Build**: Execute each task with memory injection
4. **Observe**: Extract failures and patterns

### Standalone Commands

```
/helix-query <text>    # Search memory by meaning
/helix-stats           # Memory health and statistics
```

## Memory System

### Scoring

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)

effectiveness = helped / (helped + failed)
recency = 2^(-days_since_use / 7)
```

### Operations

```bash
# Store
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py store \
    --trigger "situation" --resolution "action" --type failure

# Recall
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py recall "query" --limit 5

# Feedback
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py feedback \
    --utilized '["mem-1"]' --injected '["mem-1", "mem-2"]'

# Health
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py health
```

### Feedback Loop

After task execution:
- Utilized memories → `helped++`
- Injected but unused → `failed++`

Effective memories rise in future rankings. Ineffective ones sink.

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── agents/
│   ├── explorer.md           # Context gathering (haiku)
│   ├── planner.md            # Task decomposition (opus)
│   ├── builder.md            # Task execution (opus)
│   └── observer.md           # Learning extraction (opus)
├── lib/
│   ├── memory/
│   │   ├── __init__.py       # Clean exports
│   │   ├── core.py           # store, recall, feedback, chunk, etc.
│   │   ├── embeddings.py     # Semantic search
│   │   └── meta.py           # Metacognition
│   ├── db/
│   │   └── connection.py     # SQLite with unified schema
│   ├── exploration.py        # Exploration storage
│   ├── plan.py               # Plan management
│   └── workspace.py          # Task execution context
├── scripts/
│   ├── setup-env.sh          # SessionStart hook
│   └── inject-context.py     # PreToolUse hook
├── skills/
│   ├── helix/
│   │   └── SKILL.md          # Main orchestrator
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
└── README.md
```

## Database

Single SQLite database at `.helix/helix.db`:

| Table | Purpose |
|-------|---------|
| memory | Failures and patterns with embeddings |
| memory_edge | Relationships between memories |
| exploration | Gathered context |
| plan | Task decompositions |
| workspace | Task execution contexts |

## License

MIT
