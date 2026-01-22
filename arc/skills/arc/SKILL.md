# Arc (Evolved)

> Think deeply. Act precisely. Learn automatically. Know when to pivot.

*Evolved through synthesis of Claude Flow, Ralph Wiggum, Mem0, cognitive architectures (SOAR/ACT-R), and hard lessons from AutoGPT.*

---

## The Evolved Loop

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

**REASON**: Understand, assess, decide. *Detect impasse explicitly.* (SOAR pattern)
**ACT**: Execute with focus. *Backpressure gates verify.* (Ralph pattern)
**LEARN**: Extract, chunk, decay. *Convert experience to rules.* (Cognitive pattern)
**METACOGNITION**: Monitor approach. *Know when to pivot.* (Meta-AQUA pattern)

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
   │  - Should we pivot? (AutoGPT lesson: compound errors kill)
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
   │  Memory retrieval is activation-based (ACT-R pattern):
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
   │  Output options (SOAR pattern):
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
   │  Backpressure (Ralph pattern):
   │  - Verification failure = task NOT complete
   │  - Loop: fix → re-verify until pass or BLOCKED
   │  - Gates create learning, not just quality
   │
   │  Feedback loop closes automatically:
   │  - utilized memories → helped++
   │  - injected but unused → failed++
   │
   ▼
4. LEARN (automatic + evolved)
   │
   │  On BLOCKED:
   │  - Extract failure pattern → store in memory
   │  - Record outcome for metacognition
   │
   │  On DELIVERED:
   │  - CHUNK the success (SOAR pattern)
   │  - Extract: "this approach worked for this situation"
   │  - Store as pattern, or strengthen existing similar pattern
   │  - Record outcome for metacognition
   │
   │  Memory maintenance:
   │  - Effectiveness updates (helped/failed)
   │  - DECAY unused memories (Mem0 pattern)
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

### Adaptive Depth (Original)

The REASON phase naturally scales:
- Simple objective → Simple assessment → One task
- Complex objective → Deep analysis → Multiple tasks

No artificial forcing. Complexity emerges from the objective, not from the system.

### Automatic Feedback (Original)

You don't have to remember to close the loop. The task completion automatically triggers feedback. This is critical - manual feedback is forgotten, automatic feedback compounds.

### Memory as Intelligence (Original)

The agents themselves are stateless. The memory is where intelligence accumulates.

Each session:
1. Queries memory → gets relevant context
2. Uses (or doesn't use) that context
3. Reports what was utilized
4. Memory effectiveness updates
5. Next session gets better-ranked context

This is compounding intelligence. Not in the agent. In the system.

### Honest Reporting (Original)

BLOCKED is not failure. BLOCKED with clear information is valuable learning.

The ACT agent is instructed to report honestly. UTILIZED must be accurate. This creates signal, not noise.

---

## Evolved Patterns (From Research Synthesis)

### Impasse Detection (SOAR)

Most agents don't know they're stuck. They generate plausible-sounding output instead of admitting "I don't know how to proceed."

Arc's REASON agent can output IMPASSE with explicit type and subgoal. This is how expertise develops - not by pretending to know, but by recognizing gaps and addressing them.

### Backpressure Gates (Ralph Wiggum)

"Backpressure over prescription." Instead of prescribing exactly how to do things, create gates that reject bad work.

Verification isn't optional quality control. It's how learning happens. When verification fails, that's signal. The ACT agent must loop until verification passes or explicitly BLOCK.

### Chunking (SOAR/ACT-R)

When deliberate problem-solving succeeds, compile that experience into a rule.

Arc's `chunk()` function:
- Takes successful task completion
- Extracts "this approach worked for this situation"
- Stores as pattern (or strengthens existing similar pattern)
- Next time → rule fires directly, no deliberation needed

This is how expertise develops: slow reasoning → fast intuition.

### Memory Decay (Mem0)

Memories that aren't used should fade. Without decay, memory bloats with noise.

Arc's `decay()` function:
- Applies half-life to recency score
- Unused memories gradually lose activation
- Recall now weighs: relevance × effectiveness × recency

This mirrors human memory - things you use stay accessible, things you don't fade.

### Metacognition (Cognitive Architecture)

Thinking about thinking. The agent monitors its own reasoning process.

Arc's metacognitive layer:
- Tracks success/failure per session
- Detects when approach isn't working (consecutive failures)
- Recommends pivot before compound errors kill the session

The AutoGPT lesson: if you've failed 3 times with the same approach, the 4th attempt probably won't work either.

### Activation-Based Retrieval (ACT-R)

Memory retrieval isn't just similarity. It's:

```
activation = base_level + spreading_activation + noise
```

Simplified for Arc:
```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)
```

This explains why some memories are recalled instantly while others require effort. Frequently used, effective, recent memories are more accessible.

### Fresh Context Option (Ralph)

Sometimes the best move is to start fresh. Context rot is real - accumulated errors compound.

Arc supports the Ralph pattern: clear session, start fresh, let git/files be the persistent state.

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

The REASON agent thinks - and knows when it's stuck.
The ACT agent does - with backpressure gates that verify.
The memory compounds - with decay and chunking.
The metacognition monitors - knowing when to pivot.

Over time, the system develops judgment - not through complex rules, but through accumulated experience with honest feedback, explicit impasse recognition, and automatic pattern extraction.

That's the arc of learning.

---

## Research Heritage

Arc synthesizes insights from:

| Source | Contribution |
|--------|--------------|
| **Claude Flow** | Memory as infrastructure, pattern confidence, smart routing |
| **Ralph Wiggum** | Fresh context, backpressure over prescription, git as memory |
| **Mem0** | Extract facts not conversations, decay, consolidation |
| **LangGraph** | State machines, checkpointing, cycles are first-class |
| **SOAR** | Impasse detection, chunking, subgoal creation |
| **ACT-R** | Activation-based retrieval, frequency+recency weighting |
| **AutoGPT lessons** | Bounded autonomy, compound errors, human checkpoints |
| **Cognitive architectures** | Dual-process thinking, metacognition, production rules |

The goal was never to copy these systems. It was to find the patterns underneath - the principles that make learning agents actually work.

Arc is what emerged.
