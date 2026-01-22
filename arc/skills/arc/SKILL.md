# Arc

> Think deeply. Act precisely. Learn automatically.

---

## The Loop

```
           ┌─────────────────────────────────────────┐
           │                                         │
           │   REASON ───────▶ ACT ───────▶ LEARN   │
           │      │                           │      │
           │      │                           │      │
           │      └───────── memory ──────────┘      │
           │                                         │
           │   Where each cycle makes the next       │
           │   cycle smarter.                        │
           │                                         │
           └─────────────────────────────────────────┘
```

**REASON**: Understand what's needed. Assess complexity. Decide approach.
**ACT**: Execute with focus. Stay in scope. Report honestly.
**LEARN**: Extract knowledge. Update effectiveness. Compound wisdom.

---

## Commands

| Command | What it does |
|---------|--------------|
| `/arc <objective>` | Full loop: reason → act → learn |
| `/arc:think <objective>` | Just reasoning (no execution) |
| `/arc:recall <query>` | Search memory by meaning |
| `/arc:health` | Learning system status |

---

## Flow

### /arc \<objective\>

The full loop.

```
1. BUILD CONTEXT
   │
   │  Gather what we know:
   │  - Query memory for relevant failures and patterns
   │  - Assess codebase structure
   │  - Evaluate complexity signals
   │
   ▼
2. REASON
   │
   │  Think through the objective:
   │  - What's being asked?
   │  - How complex is it?
   │  - What's the approach?
   │
   │  Output: Assessment + Tasks (1 or more)
   │
   ▼
3. ACT (for each task)
   │
   │  Execute with context:
   │  - Inject relevant memories
   │  - Do the work
   │  - Verify the result
   │  - Report: DELIVERED or BLOCKED
   │  - Report: what memories were UTILIZED
   │
   │  Feedback loop closes automatically:
   │  - utilized memories → helped++
   │  - injected but unused → failed++
   │
   ▼
4. LEARN (automatic)
   │
   │  If task blocked:
   │  - Extract failure pattern → store in memory
   │
   │  Memory effectiveness updates:
   │  - Memories that help rise in ranking
   │  - Memories that don't help fall
   │
   ▼
5. SUMMARIZE
   │
   │  Report what happened.
   │  Show learning loop status.
   │
   done
```

### /arc:think \<objective\>

Just reasoning, no execution. Useful for planning.

```
1. BUILD CONTEXT
   ▼
2. REASON
   ▼
3. OUTPUT reasoning result
   (no ACT, no LEARN)
```

### /arc:recall \<query\>

Search memory by meaning.

```
python3 $PLUGIN_ROOT/lib/memory.py recall "<query>"
```

Returns memories ranked by relevance × effectiveness.

### /arc:health

Check learning system status.

```
python3 $PLUGIN_ROOT/lib/memory.py health
```

Shows:
- Total memories
- By type (failures, patterns)
- Effectiveness
- Feedback status
- Issues

---

## Execution Detail

### Building Context

```bash
# Get memory context
python3 $PLUGIN_ROOT/lib/context.py "<objective>"
```

Returns:
```json
{
  "objective": "...",
  "memory": {
    "failures": [...],
    "patterns": [...],
    "connected": [...],
    "injected_names": [...]
  },
  "codebase": {...},
  "complexity": {...}
}
```

### Launching Reason

```
Task(arc:arc-reason)
INPUT:
  OBJECTIVE: <objective>
  MEMORY: <context.memory>
  CODEBASE: <context.codebase>
  COMPLEXITY: <context.complexity>
```

Reason outputs:
- Assessment (simple/moderate/complex/unclear)
- Tasks (1 or more)
- Memory application notes
- Reasoning

### Launching Act (per task)

```
Task(arc:arc-act)
INPUT:
  TASK:
    objective: <task.objective>
    delta: <task.delta>
    verify: <task.verify>
  MEMORIES:
    failures: <relevant failures>
    patterns: <relevant patterns>
  LINEAGE: <previous task deliveries if any>
```

Act outputs:
- DELIVERED or BLOCKED
- Details
- UTILIZED list

### Automatic Feedback

On task completion (DELIVERED or BLOCKED):

```bash
python3 $PLUGIN_ROOT/lib/task.py complete \
  --session "$SESSION" \
  --seq $SEQ \
  --delivered "$DELIVERED" \
  --utilized '$UTILIZED_JSON'
```

This automatically calls `memory.feedback(utilized, injected)`:
- Memories in utilized → `helped++`
- Memories in injected but not utilized → `failed++`

The loop closes without manual intervention.

### Learning Extraction

On BLOCKED:

```bash
python3 $PLUGIN_ROOT/lib/memory.py store \
  --type failure \
  --trigger "<error/obstacle summary>" \
  --resolution "<what should be done differently>" \
  --source "$SESSION-$SEQ"
```

This captures the lesson for future sessions.

---

## State Diagram

```
     ┌──────────┐
     │   INIT   │
     └────┬─────┘
          │
          ▼
     ┌──────────┐
     │ CONTEXT  │  Build context from memory + codebase
     └────┬─────┘
          │
          ▼
     ┌──────────┐
     │  REASON  │  Adaptive thinking
     └────┬─────┘
          │
    ┌─────┴─────┐
    │           │
    ▼           ▼
┌───────┐  ┌─────────┐
│UNCLEAR│  │  ACT    │◀─┐
└───┬───┘  └────┬────┘  │
    │           │       │
    ▼           │       │
┌───────┐       │       │
│ ASK   │       │       │
└───────┘  ┌────┴────┐  │
           │         │  │
           ▼         ▼  │
       ┌──────┐  ┌──────┴─┐
       │ DONE │  │  NEXT  │
       └──┬───┘  └────────┘
          │
          ▼
     ┌──────────┐
     │  LEARN   │  Automatic extraction + feedback
     └────┬─────┘
          │
          ▼
     ┌──────────┐
     │ SUMMARY  │
     └──────────┘
```

---

## Why This Works

### Adaptive Depth

The REASON phase naturally scales:
- Simple objective → Simple assessment → One task
- Complex objective → Deep analysis → Multiple tasks

No artificial forcing. Complexity emerges from the objective, not from the system.

### Automatic Feedback

You don't have to remember to close the loop. The task completion automatically triggers feedback. This is critical - manual feedback is forgotten, automatic feedback compounds.

### Memory as Intelligence

The agents themselves are stateless. The memory is where intelligence accumulates.

Each session:
1. Queries memory → gets relevant context
2. Uses (or doesn't use) that context
3. Reports what was utilized
4. Memory effectiveness updates
5. Next session gets better-ranked context

This is compounding intelligence. Not in the agent. In the system.

### Honest Reporting

BLOCKED is not failure. BLOCKED with clear information is valuable learning.

The ACT agent is instructed to report honestly. UTILIZED must be accurate. This creates signal, not noise.

---

## Environment

```bash
PLUGIN_ROOT = <from .arc/plugin_root>
ARC_DB_PATH = <optional: custom database path>
```

Storage: `.arc/arc.db` (SQLite with WAL)

---

## The Point

Arc is not about following a process. Arc is about thinking well and learning from experience.

The REASON agent thinks. The ACT agent does. The memory compounds.

Over time, the system develops judgment - not through complex rules, but through accumulated experience with honest feedback.

That's the arc of learning.
