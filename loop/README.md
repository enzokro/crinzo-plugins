# Loop

**Self-learning orchestrator for Claude Code.**

Remembers what hurt. Remembers what helped. Gets better by tracking which memories matter.

## The Core Idea

The agent doesn't learn. The memory system that wraps the agent learns.

```
BEFORE → DURING → AFTER → FEEDBACK → REPEAT
   │         │        │         │
   │         │        │         └── Update memory effectiveness
   │         │        └── Extract new knowledge from failures
   │         └── Execute task with injected context
   └── Query memory for relevant knowledge
```

## Installation

```bash
# The plugin is installed via Claude Code plugin system
# Ensure sentence-transformers is available for semantic search:
pip install sentence-transformers
```

## Usage

### Execute a Task with Learning

```
/loop implement user authentication with JWT
```

This will:
1. Query memory for relevant failures and patterns
2. Inject that context into the executor
3. Execute the task
4. Extract any failures as new memories
5. Update memory effectiveness based on what was actually used

### Search Memory

```
/loop:query authentication errors
```

### Check System Health

```
/loop:stats
```

### Clean Ineffective Memories

```
/loop:prune
```

## How Learning Works

### 1. Memory Storage

Memories are stored with semantic embeddings:

```python
Memory(
    name="jwt-expiry-validation",
    type="failure",
    trigger="JWT token expired but code didn't check exp claim",
    resolution="Always validate exp claim before using token",
    embedding=<384-dim vector>,
    helped=5,    # times this memory proved useful
    failed=1,    # times injected but not used
)
```

### 2. Context Injection

Before each task, relevant memories are queried by semantic similarity:

```python
failures = memory.query(task, type="failure", limit=5)
patterns = memory.query(task, type="pattern", limit=3)
```

### 3. Utilization Tracking

The executor reports which memories actually helped:

```
DELIVERED: Implemented JWT authentication

UTILIZED:
- jwt-expiry-validation: Applied exp claim check as suggested
- pytest-fixture-scope: Used module-scoped fixtures for auth setup
```

### 4. Feedback Loop

Memories are updated based on utilization:

```python
memory.feedback(
    utilized=["jwt-expiry-validation", "pytest-fixture-scope"],
    injected=["jwt-expiry-validation", "pytest-fixture-scope", "api-rate-limiting"]
)
# jwt-expiry-validation.helped += 1
# pytest-fixture-scope.helped += 1
# api-rate-limiting.failed += 1  (injected but not used)
```

### 5. Effectiveness Ranking

Next time, memories are ranked by `relevance × effectiveness`:

- Memories that help → rise in ranking → get injected more
- Memories that don't help → fall in ranking → stop being injected
- Natural selection for knowledge

## File Structure

```
loop/
├── .claude-plugin/
│   └── plugin.json          # Plugin manifest
├── agents/
│   └── executor.md          # Task executor with memory context
├── lib/
│   ├── memory.py            # Core memory operations (6 functions)
│   └── db/
│       ├── connection.py    # SQLite setup
│       ├── schema.py        # Memory dataclass
│       └── embeddings.py    # Semantic similarity
├── scripts/
│   └── setup-env.sh         # Session initialization
├── skills/
│   └── loop/
│       └── SKILL.md         # Main orchestrator
└── requirements.txt
```

## The Essential API

```python
# Store knowledge
memory.add(trigger, resolution, type="failure"|"pattern")

# Retrieve by meaning
memory.query(text, type=None, limit=5)

# Record feedback
memory.feedback(utilized=[], injected=[])

# Remove ineffective memories
memory.prune(min_effectiveness=0.25)

# Check system health
memory.stats()
memory.verify()
```

## Philosophy

> Mistakes are expensive. Don't make the same one twice.
> Successes are valuable. Repeat what works.
> Relevance is contextual. Similar problems need similar solutions.
> Effectiveness is earned. Prove yourself through use.

The system gets smarter over time, automatically, through the feedback loop.

## State

All state is stored in `.loop/`:
- `memory.db` - SQLite database with memories
- `plugin_root` - Path to plugin installation
- `sessions.log` - Session history

## License

MIT
