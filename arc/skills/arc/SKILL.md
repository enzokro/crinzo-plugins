# Arc

A learning layer for Claude Code. Memory that compounds. Metacognition that knows when to pivot.

---

## What Arc Is

Arc is not an orchestrator. It's a set of tools that make Claude Code smarter over time:

**Memory** (`lib/memory.py`)
- Stores failures and patterns
- Retrieves by relevance × effectiveness × recency
- Automatically updates effectiveness based on what you actually use
- Decays unused memories, consolidates similar ones

**Metacognition** (`lib/meta.py`)
- Tracks success/failure across a session
- Detects when your approach is failing
- Recommends pivot before compound errors kill you

**Context** (`lib/context.py`)
- Builds context from memory + codebase signals
- Assesses complexity

**Task Tracking** (`lib/task.py`)
- Tracks tasks within a session
- Closes feedback loop automatically on completion

---

## Commands

```bash
# Query memory
/arc:recall <query>

# Check if your approach is working
/arc:meta

# Learning system health
/arc:health

# After success - extract pattern
/arc:chunk

# Maintenance
/arc:decay
/arc:consolidate
```

---

## How to Use Arc

### Starting Work

Before diving into a task, query memory:

```bash
python3 $ARC_ROOT/lib/memory.py recall "your objective here"
```

You'll get relevant failures (things to avoid) and patterns (approaches that worked).

If continuing a session, check metacognition:

```bash
python3 $ARC_ROOT/lib/meta.py assess --session "$SESSION"
```

If it says "pivot_now" - stop. Your approach isn't working. Try something different.

### While Working

**When you're stuck**: Don't hallucinate forward. Recognize the impasse:
- Is this a "no_approach" (genuinely don't know how)?
- A "conflict" (contradicting requirements)?
- A "missing_capability" (need something unavailable)?
- A "repeated_failure" (tried and failed, trying again won't help)?

Name it. Create a subgoal to resolve it. Or ask for help.

**When you complete something**: Report honestly what memories you actually used.

```bash
python3 $ARC_ROOT/lib/task.py complete \
  --session "$SESSION" \
  --seq $SEQ \
  --delivered "what you delivered" \
  --utilized '["memory-names-that-helped"]'
```

This automatically updates memory effectiveness. Memories you used get stronger. Memories you didn't use get weaker.

**When you fail**: Store the failure so you don't repeat it:

```bash
python3 $ARC_ROOT/lib/memory.py store \
  --type failure \
  --trigger "what went wrong" \
  --resolution "what to do instead"
```

### After Success

Extract a pattern from what worked:

```bash
python3 $ARC_ROOT/lib/memory.py chunk \
  --task "the objective" \
  --outcome "SUCCESS" \
  --approach "what you did that worked"
```

This creates a reusable pattern, or strengthens an existing similar one.

---

## The Actual API

### memory.py

```python
# Store a failure or pattern
store(trigger, resolution, type="failure"|"pattern") → name

# Find relevant memories
recall(query, type=None, limit=10) → [memories ranked by score]

# Close feedback loop
feedback(utilized=["names"], injected=["names"]) → {helped, unhelpful}

# Connect related memories
relate(name_a, name_b, type="similar"|"causes"|"solves")

# Get connected memories
connected(name) → [related memories]

# Remove ineffective memories
prune(threshold=0.3) → {pruned, remaining}

# System health
health() → {total, effectiveness, issues}

# Decay unused memories
decay(threshold_days=30) → {candidates}

# Extract pattern from success
chunk(task, outcome, approach) → {status, name}

# Merge similar memories
consolidate(similarity=0.9) → {merged, remaining}
```

### meta.py

```python
# Track outcome
record_outcome(session_id, task_seq, success, notes="")

# Is approach working?
assess_approach(session_id) → {status, success_rate, recommendation}

# Should I pivot?
should_pivot(session_id) → {should_pivot, confidence, suggestion}

# Session summary
session_summary(session_id) → {tasks, success_rate, failure_notes}

# Start fresh
clear_session(session_id)
```

### context.py

```python
# Build context for an objective
build(objective, quick=False) → {
  objective,
  memory: {failures, patterns, connected, injected_names},
  codebase: {structure signals},
  complexity: {level, suggested_decomposition}
}
```

### task.py

```python
# Start session
new_session() → {session_id}

# Add task
add(session_id, seq, objective, delta=[], injected=[])

# Complete task (auto-triggers feedback)
complete(session_id, seq, delivered, utilized=[]) → {status, feedback}

# Block task
block(session_id, seq, obstacle, attempted)

# Get task
get(session_id, seq) → task

# Pending tasks
pending(session_id) → [tasks]
```

---

## Principles

### Memory is where intelligence accumulates

You are stateless. Memory is not. Use it.

### Feedback must close

When you complete a task, report what memories actually helped. This is how the system learns which memories are valuable.

### Impasse is signal

When you're stuck, say so explicitly. Don't generate plausible garbage. "I don't know how to proceed" is valuable. It creates a subgoal.

### Verification is learning

When verification fails, that's information. Loop until it passes, or explicitly block with why.

### Decay is healthy

Memories you don't use should fade. Don't fight it. Let relevance emerge from usage.

### Know when to pivot

If you've failed 3 times with the same approach, the 4th attempt probably won't work either. Check metacognition. Start fresh if needed.

---

## Environment

```bash
ARC_ROOT=/path/to/arc        # Plugin root
ARC_DB_PATH=.arc/arc.db      # Optional: custom db path
```

Storage: SQLite with WAL mode at `.arc/arc.db`

---

## That's It

Arc is a learning layer. Query memory before you start. Report honestly when you finish. Extract patterns from success. Recognize when you're stuck.

The intelligence compounds in the memory, not in elaborate orchestration.

Use the tools. Get smarter over time.
