# Helix

**Advanced self-learning orchestrator for Claude Code.**

Learning spirals upward. Each cycle builds on the last.

## Overview

Helix extends the core learning loop with sophisticated components:

```
EXPLORE → PLAN → BUILD* → OBSERVE → FEEDBACK
   │                          │          │
   │         memories         │          │
   └──────────────────────────┴──────────┘
```

- **Explorer**: Gathers context (structure, patterns, memory, targets)
- **Planner**: Decomposes objectives into executable tasks
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
1. **Explore**: Gather codebase context
2. **Plan**: Decompose into tasks with dependencies
3. **Build**: Execute each task with memory injection
4. **Observe**: Extract failures and patterns
5. **Feedback**: Update memory effectiveness

### Individual Commands

```
/helix:explore <objective>   # Just exploration
/helix:plan                  # Plan using recent exploration
/helix:query <text>          # Search memory
/helix:stats                 # Memory health
/helix:observe               # Extract learning manually
```

## How It Works

### 1. Exploration

The Explorer gathers:
- **Structure**: What exists in the codebase
- **Patterns**: Framework detection, idioms
- **Memory**: Relevant failures and patterns from history
- **Targets**: Files and functions to change

### 2. Planning

The Planner creates a task DAG:
- Decomposes complex objectives
- Sets dependencies (parallel where possible)
- Assigns tool budgets
- Defines verification commands

### 3. Building

For each task, the Builder:
- Receives workspace with injected memories
- Executes within constraints (delta scope, budget)
- Reports DELIVERED or BLOCKED
- Tracks which memories were UTILIZED

### 4. Observation

The Observer extracts:
- **Failures**: From blocked tasks
- **Patterns**: From high-scoring completions
- **Relationships**: Co-occurrence, causation, solutions

### 5. Feedback Loop

After execution:
- Utilized memories → helped++
- Injected but unused → failed++
- Effectiveness = helped / (helped + failed)
- Future queries rank by relevance × effectiveness

## Memory System

### Semantic Search

Memories are stored with 384-dimensional embeddings.
Queries find relevant knowledge by meaning, not keywords.

### Effectiveness Tracking

```python
Memory:
  helped: int     # Times this memory proved useful
  failed: int     # Times injected but not used
  effectiveness: float  # helped / (helped + failed)
```

### Graph Relationships

```python
MemoryEdge:
  from_name: str
  to_name: str
  rel_type: "co_occurs" | "causes" | "solves" | "similar"
  weight: float
```

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── agents/
│   ├── explorer.md          # Context gathering
│   ├── planner.md           # Task decomposition
│   ├── builder.md           # Task execution
│   └── observer.md          # Learning extraction
├── lib/
│   ├── memory.py            # Core memory operations
│   ├── exploration.py       # Exploration storage
│   ├── plan.py              # Plan management with DAG
│   ├── workspace.py         # Task execution context
│   └── db/
│       ├── connection.py    # SQLite setup
│       ├── schema.py        # Data models
│       └── embeddings.py    # Semantic similarity
├── scripts/
│   └── setup-env.sh         # SessionStart hook
├── skills/
│   └── helix/
│       └── SKILL.md         # Main orchestrator
├── README.md
└── requirements.txt
```

## Core API

### Memory

```python
# Store knowledge
memory.add(trigger, resolution, type="failure"|"pattern")

# Retrieve by meaning
memory.query(text, type=None, limit=5)

# Record feedback
memory.feedback(utilized=[], injected=[])

# Create relationships
memory.relate(from_name, to_name, rel_type)

# Graph traversal
memory.related(name, max_hops=2)

# Maintenance
memory.prune(min_effectiveness=0.25)
memory.stats()
memory.verify()
```

### Plan

```python
# Save plan
plan.save(plan_dict)

# Load active plan
plan.load()

# Update task status
plan.update_task(plan_id, task_seq, updates)

# Get executable tasks
plan.ready_tasks()

# Check for stuck plans
plan.cascade_status()
```

### Workspace

```python
# Create with memory injection
workspace.create(plan_id, task, framework, idioms)

# Complete with feedback
workspace.complete(workspace_id, delivered, utilized)

# Block with feedback
workspace.block(workspace_id, reason, utilized)
```

## Philosophy

> The agent doesn't learn. The memory system that wraps the agent learns.

Each session:
1. Benefits from previous sessions' memories
2. Contributes new memories for future sessions
3. Feedback adjusts memory rankings
4. Ineffective memories fade, effective ones rise

**This is how learning compounds.**

## License

MIT
