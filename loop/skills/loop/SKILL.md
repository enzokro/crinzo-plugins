# Loop - Self-Learning Orchestrator

> Remembers what hurt. Remembers what helped. Gets better by tracking which memories matter.

## Philosophy

The agent doesn't learn. The memory system that wraps the agent learns.
Each execution:
1. **INJECT** relevant knowledge before the task
2. **EXECUTE** the task with that knowledge
3. **EXTRACT** new knowledge from the outcome
4. **FEEDBACK** update memory effectiveness based on what was actually used

The learning compounds across sessions through this closed loop.

---

## Commands

### `/loop <task>` - Execute with Learning

The main command. Runs a task with memory injection and feedback.

### `/loop:query <text>` - Search Memory

Find memories relevant to a query.

### `/loop:stats` - Memory Health

Show statistics about the learning system.

### `/loop:prune` - Clean Memory

Remove memories that have proven ineffective.

---

## Environment

```bash
PLUGIN_ROOT   = <read from .loop/plugin_root>
LOOP_DB_PATH  = <optional: custom database path>
```

---

## State Machine

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  INJECT  │────▶│ EXECUTE  │────▶│ EXTRACT  │────▶│ FEEDBACK │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
     │                                                   │
     └───────────────── LOOP ────────────────────────────┘
```

---

## INIT

Entry point. Determine command and route.

```yaml
ENTRY:
  - CHECK: command type
  - IF: /loop <task>
    GOTO: INJECT
  - IF: /loop:query <text>
    GOTO: QUERY
  - IF: /loop:stats
    GOTO: STATS
  - IF: /loop:prune
    GOTO: PRUNE
```

---

## INJECT

Query memory for relevant context and prepare for execution.

```yaml
STATE: INJECT
GOAL: Retrieve relevant memories to inject into the task

ACTIONS:
  # 1. Query for failures (things to avoid)
  - DO: python3 $PLUGIN_ROOT/lib/memory.py query "$TASK" --type failure --limit 5
    CAPTURE: failures_json

  # 2. Query for patterns (things to apply)
  - DO: python3 $PLUGIN_ROOT/lib/memory.py query "$TASK" --type pattern --limit 3
    CAPTURE: patterns_json

  # 3. Track what was injected (for feedback later)
  - TRACK: injected_memories = [names from failures_json + patterns_json]

  # 4. Format context for executor
  - FORMAT: |
      ## TASK
      $TASK

      ## FAILURES TO AVOID
      $failures_json

      ## PATTERNS TO APPLY
      $patterns_json

NEXT: EXECUTE
```

### Context Format

The executor receives:

```markdown
## TASK
<the user's task>

## FAILURES TO AVOID
[
  {"name": "...", "trigger": "...", "resolution": "...", "effectiveness": 0.8},
  ...
]

## PATTERNS TO APPLY
[
  {"name": "...", "trigger": "...", "resolution": "...", "effectiveness": 0.7},
  ...
]
```

---

## EXECUTE

Run the executor agent with injected context.

```yaml
STATE: EXECUTE
GOAL: Complete the task using injected knowledge

ACTIONS:
  # Launch executor agent with context
  - DO: Task(loop:loop-executor) with formatted context
    CAPTURE: executor_output

  # Parse outcome
  - PARSE: executor_output for:
      - DELIVERED: summary (success)
      - BLOCKED: reason (failure)
      - UTILIZED: list of memory names used

  - IF: DELIVERED found
    TRACK: outcome = "success"
    TRACK: delivered = summary
    TRACK: utilized = parsed UTILIZED list
    GOTO: FEEDBACK

  - IF: BLOCKED found
    TRACK: outcome = "failure"
    TRACK: blocked_reason = reason
    TRACK: utilized = parsed UTILIZED list
    GOTO: EXTRACT
```

---

## EXTRACT

Extract learnable knowledge from failures.

```yaml
STATE: EXTRACT
GOAL: Capture failure as new memory for future avoidance

CONDITION: outcome == "failure"

ACTIONS:
  # Extract failure pattern
  - ANALYZE: blocked_reason to identify:
      - trigger: what condition caused this?
      - resolution: how should future attempts handle this?

  # Add to memory (if novel)
  - DO: python3 $PLUGIN_ROOT/lib/memory.py add \
        --trigger "$trigger" \
        --resolution "$resolution" \
        --type failure \
        --source "$TASK"
    CAPTURE: add_result

  - IF: add_result.status == "added"
    OUTPUT: "📝 Learned new failure pattern: {add_result.name}"

  - IF: add_result.status == "merged"
    OUTPUT: "🔄 Merged with existing: {add_result.name}"

NEXT: FEEDBACK
```

### Failure Extraction Template

When a task fails, extract:

```yaml
trigger: |
  <First line of error or blocking reason>
  <Key identifying characteristics>

resolution: |
  <What should be done differently>
  <Specific fix or avoidance strategy>
```

---

## FEEDBACK

Close the learning loop by recording what actually helped.

```yaml
STATE: FEEDBACK
GOAL: Update memory effectiveness based on utilization

ACTIONS:
  # Record feedback
  - DO: python3 $PLUGIN_ROOT/lib/memory.py feedback \
        --utilized '$utilized_json' \
        --injected '$injected_json'
    CAPTURE: feedback_result

  # Report
  - IF: feedback_result.helped > 0
    OUTPUT: "✓ {feedback_result.helped} memories proved helpful"

  - IF: feedback_result.not_helped > 0
    OUTPUT: "○ {feedback_result.not_helped} memories not used this time"

NEXT: COMPLETE
```

---

## COMPLETE

Final state. Report outcome.

```yaml
STATE: COMPLETE

ACTIONS:
  - IF: outcome == "success"
    OUTPUT: |
      ✓ Task completed

      Delivered: $delivered

      Learning loop: $feedback_result

  - IF: outcome == "failure"
    OUTPUT: |
      ✗ Task blocked

      Reason: $blocked_reason

      Extracted: $add_result
      Learning loop: $feedback_result
```

---

## QUERY

Handle `/loop:query <text>` - search memory by meaning.

```yaml
STATE: QUERY
GOAL: Find memories relevant to query

ACTIONS:
  - DO: python3 $PLUGIN_ROOT/lib/memory.py query "$QUERY_TEXT" --limit 10
    CAPTURE: results

  - OUTPUT: |
      ## Memory Search: "$QUERY_TEXT"

      $results

      (Sorted by relevance × effectiveness)
```

---

## STATS

Handle `/loop:stats` - memory health metrics.

```yaml
STATE: STATS
GOAL: Show learning system health

ACTIONS:
  - DO: python3 $PLUGIN_ROOT/lib/memory.py stats
    CAPTURE: stats

  - DO: python3 $PLUGIN_ROOT/lib/memory.py verify
    CAPTURE: verify

  - OUTPUT: |
      ## Loop Memory Statistics

      **Total memories**: $stats.total
      - Failures: $stats.by_type.failure.count
      - Patterns: $stats.by_type.pattern.count

      **Effectiveness**
      - Overall: $stats.overall_effectiveness
      - With feedback: $stats.with_feedback
      - Without feedback: $stats.without_feedback

      **Learning Loop**: $verify.status
      $verify.issues
```

---

## PRUNE

Handle `/loop:prune` - remove ineffective memories.

```yaml
STATE: PRUNE
GOAL: Clean out memories that don't help

ACTIONS:
  # Show what will be pruned
  - DO: python3 $PLUGIN_ROOT/lib/memory.py stats
    CAPTURE: before_stats

  # Prune
  - DO: python3 $PLUGIN_ROOT/lib/memory.py prune --min-effectiveness 0.25 --min-uses 3
    CAPTURE: prune_result

  - OUTPUT: |
      ## Memory Pruning Complete

      Removed: $prune_result.pruned ineffective memories
      Remaining: $prune_result.remaining

      Pruned (effectiveness < 25%):
      $prune_result.pruned_names
```

---

## Pattern Extraction (Success Cases)

When a task succeeds with notable technique, optionally extract a pattern:

```yaml
CONDITION: outcome == "success" AND novel_technique_detected

ACTIONS:
  - ANALYZE: delivered to identify:
      - trigger: when does this technique apply?
      - resolution: what is the technique?

  - DO: python3 $PLUGIN_ROOT/lib/memory.py add \
        --trigger "$trigger" \
        --resolution "$resolution" \
        --type pattern \
        --source "$TASK"

  - OUTPUT: "📝 Learned new pattern: {name}"
```

---

## Error Recovery

```yaml
STATE: ERROR
TRIGGER: Any unhandled exception

ACTIONS:
  - LOG: error details to .loop/loop.log
  - OUTPUT: "Error: {error_message}"
  - OUTPUT: "Memory state preserved. Run /loop:stats to check health."
```

---

## The Core Loop Summarized

```
    ┌─────────────────────────────────────────────────┐
    │                                                 │
    │   BEFORE: query(task) → inject context          │
    │                                                 │
    │   DURING: execute(task, context)                │
    │                                                 │
    │   AFTER:  if failed → extract(failure)          │
    │           feedback(utilized, injected)          │
    │                                                 │
    │   RESULT: memories that helped → rank higher    │
    │           memories that didn't → rank lower     │
    │           new failures → stored for avoidance   │
    │                                                 │
    │   NEXT:   better context → better execution     │
    │                                                 │
    └─────────────────────────────────────────────────┘
```

The system gets smarter over time, automatically, through this feedback loop.
