# Arc

> Think deeply. Act precisely. Learn automatically. Know when to pivot.

---

## The Loop

```
         ┌─────────────────────────────────────────────┐
         │              METACOGNITION                   │
         │   "Is this approach working? Should I pivot?"│
         └──────────────────────┬──────────────────────┘
                                │ monitors
                                ▼
    ┌──────────┐      ┌──────────────┐      ┌──────────────┐
    │  REASON  │─────▶│     ACT      │─────▶│    LEARN     │
    │          │      │              │      │              │
    │ Impasse? │      │ Backpressure │      │ Chunk+Decay  │
    │ →subgoal │      │    gates     │      │   →memory    │
    └──────────┘      └──────────────┘      └──────────────┘
          ▲                                        │
          └─────────── memory (weighted) ◀─────────┘
                   relevance × effectiveness × recency
```

**REASON**: Understand, assess, decide. Detect impasse explicitly.
**ACT**: Execute with focus. Backpressure gates verify.
**LEARN**: Extract, chunk, decay. Convert experience to rules.
**METACOGNITION**: Monitor approach. Know when to pivot.

---

## Commands

| Command | What it does |
|---------|--------------|
| `/arc <objective>` | Full loop: reason → act → learn |
| `/arc:think <objective>` | Just reasoning (no execution) |
| `/arc:recall <query>` | Search memory by meaning |
| `/arc:health` | Learning system status |
| `/arc:meta <session>` | Metacognitive assessment - is approach working? |
| `/arc:chunk` | Extract patterns from successful session |
| `/arc:decay` | Apply memory decay to unused memories |
| `/arc:consolidate` | Merge similar memories |

---

## Flow

### /arc \<objective\>

The full evolved loop.

```
0. METACOGNITIVE CHECK (if continuing session)
   │
   │  Before diving in:
   │  - How many recent failures?
   │  - Is current approach working?
   │  - Should we pivot? (compound errors kill)
   │
   │  If pivot recommended → flag for user, suggest alternatives
   │
   ▼
1. BUILD CONTEXT
   │
   │  Gather what we know:
   │  - Query memory for relevant failures and patterns
   │  - Assess codebase structure
   │  - Evaluate complexity signals
   │
   │  Memory retrieval is activation-based:
   │  score = relevance × effectiveness × recency
   │
   ▼
2. REASON
   │
   │  Think through the objective:
   │  - What's being asked?
   │  - How complex is it?
   │  - What's the approach?
   │
   │  Output options:
   │  - Assessment + Tasks (normal)
   │  - IMPASSE (explicit recognition of being stuck)
   │
   │  Impasse types:
   │  - no_approach: genuinely don't know how
   │  - conflict: contradicting requirements
   │  - missing_capability: need something unavailable
   │  - repeated_failure: tried and failed multiple times
   │
   │  On impasse → create SUBGOAL for resolution
   │
   ▼
3. ACT (for each task)
   │
   │  Execute with context:
   │  - Check metacognitive state
   │  - Inject relevant memories
   │  - Do the work
   │  - VERIFY (backpressure gate - not optional!)
   │  - Report: DELIVERED or BLOCKED
   │  - Report: what memories were UTILIZED
   │
   │  Backpressure:
   │  - Verification failure = task NOT complete
   │  - Loop: fix → re-verify until pass or BLOCKED
   │  - Gates create learning, not just quality
   │
   │  Feedback loop closes automatically:
   │  - utilized memories → helped++
   │  - injected but unused → failed++
   │
   ▼
4. LEARN (automatic)
   │
   │  On BLOCKED:
   │  - Extract failure pattern → store in memory
   │  - Record outcome for metacognition
   │
   │  On DELIVERED:
   │  - CHUNK the success
   │  - Extract: "this approach worked for this situation"
   │  - Store as pattern, or strengthen existing similar pattern
   │  - Record outcome for metacognition
   │
   │  Memory maintenance:
   │  - Effectiveness updates (helped/failed)
   │  - DECAY unused memories
   │  - CONSOLIDATE similar memories
   │
   ▼
5. SUMMARIZE
   │
   │  Report what happened.
   │  Show metacognitive assessment.
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

Complexity emerges from the objective, not from the system.

### Automatic Feedback

Task completion automatically triggers feedback. Manual feedback is forgotten, automatic feedback compounds.

### Memory as Intelligence

The agents are stateless. Memory is where intelligence accumulates.

Each session:
1. Queries memory → relevant context
2. Uses (or doesn't use) that context
3. Reports what was utilized
4. Effectiveness updates
5. Next session gets better-ranked context

Compounding intelligence. Not in the agent. In the system.

### Honest Reporting

BLOCKED is not failure. BLOCKED with clear information is valuable learning.

UTILIZED must be accurate. This creates signal, not noise.

### Impasse Detection

Most agents don't know they're stuck. They generate plausible output instead of admitting "I don't know."

Arc's REASON agent can output IMPASSE with explicit type and subgoal. Recognizing gaps is how expertise develops.

### Backpressure Gates

Instead of prescribing exactly how to do things, create gates that reject bad work.

Verification isn't optional. It's how learning happens. The ACT agent must loop until verification passes or explicitly BLOCK.

### Chunking

When problem-solving succeeds, compile that experience into a rule.

Arc's `chunk()` function:
- Takes successful task completion
- Extracts "this approach worked for this situation"
- Stores as pattern (or strengthens existing similar pattern)
- Next time → fires directly, no deliberation

Slow reasoning → fast intuition.

### Memory Decay

Unused memories fade. Without decay, memory bloats with noise.

Arc's `decay()` function:
- Applies half-life to recency score
- Unused memories gradually lose activation
- Recall weighs: relevance × effectiveness × recency

### Metacognition

The agent monitors its own reasoning.

Arc's metacognitive layer:
- Tracks success/failure per session
- Detects when approach isn't working (consecutive failures)
- Recommends pivot before compound errors kill the session

If you've failed 3 times with the same approach, the 4th attempt probably won't work either.

### Activation-Based Retrieval

Memory retrieval isn't just similarity:

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)
```

Frequently used, effective, recent memories are more accessible.

### Fresh Context

Sometimes the best move is to start fresh. Context rot is real.

Clear session, start fresh, let git/files be the persistent state.

---

## Environment

```bash
PLUGIN_ROOT = <from .arc/plugin_root>
ARC_DB_PATH = <optional: custom database path>
```

Storage: `.arc/arc.db` (SQLite with WAL)

---

## The Point

Arc is about thinking well and learning from experience.

The REASON agent thinks - and knows when it's stuck.
The ACT agent does - with backpressure gates that verify.
The memory compounds - with decay and chunking.
The metacognition monitors - knowing when to pivot.

Over time, the system develops judgment through accumulated experience with honest feedback, explicit impasse recognition, and automatic pattern extraction.

That's arc.
