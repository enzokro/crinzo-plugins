# State Reference

Extended documentation for DSL variable binding, state context, and variable lifecycle.

---

## Variable Types

| Type | Declaration | Initialization | Persistence |
|------|-------------|----------------|-------------|
| **Local** | Implicit via CHECK | Each state entry | Until next GOTO |
| **Tracked** | Explicit via TRACK | First encounter (default: 0) | Entire session |

### Local Variables

Created by `CHECK:` commands that parse JSON stdout:

```
CHECK: python3 lib/orchestration.py wait-explorers
# Creates: wait_result with fields from JSON response
# Access: wait_result.status, wait_result.completed, wait_result.missing
```

Local variables are **consumed** by the next `IF:` statement and reset on `GOTO:`.

### Tracked Variables

Declared with `TRACK:` and persist across state re-entries:

```
TRACK: clarify_count
# Initializes to 0 on first encounter
# Survives GOTO PLAN → ... → GOTO PLAN
```

Modified with:
- `INCREMENT: var` — Add 1
- `SET: var = expression` — Assign value

---

## Variable Scope Reference

| Variable | Type | Used In | Purpose | Bounds |
|----------|------|---------|---------|--------|
| `clarify_count` | TRACK | PLAN_PATTERN | Prevents infinite clarification loops | Cap at 5 |
| `iteration_count` | TRACK | CAMPAIGN.EXECUTE | Bounds campaign execution | Cap at 20 |
| `prior_ready_count` | TRACK | CAMPAIGN.EXECUTE | Detects stuck state | Unchanged 3+ iterations |
| `wait_result` | Local | EXPLORE_PATTERN | Explorer quorum status | Consumed by IF |
| `decision` | Local | PLAN_PATTERN | Planner decision type | Consumed by IF |
| `ready_tasks` | Local | CAMPAIGN.EXECUTE | Tasks ready for execution | Fresh each iteration |
| `cascade` | Local | CASCADE state | Cascade analysis result | Consumed by IF |

---

## State Context Rules

### GOTO Semantics

`GOTO: STATE_NAME` creates a fresh state context:

1. **Local variables reset** — All CHECK-derived variables cleared
2. **Tracked variables persist** — TRACK declarations retain values
3. **Execution resumes** — From first instruction in target state

### State Re-Entry

When a state is re-entered (e.g., `GOTO PLAN` after clarification):

```
First entry:           TRACK: clarify_count → initializes to 0
After clarification:   GOTO PLAN → clarify_count preserved (now 1)
After 5 clarifications: clarify_count == 5 → exit with summary
```

---

## DSL Verb Extended Semantics

### DO: Command Execution

```
DO: command args
```

- Executes command, captures stdout
- Stdout available for piping to next command
- Non-zero exit triggers error handling

**Piping:**
```
DO: python3 lib/exploration.py aggregate-files
DO: | python3 lib/exploration.py write
# Second command receives first's stdout via stdin
```

### CHECK: Variable Binding

```
CHECK: command args
```

- Executes command expecting JSON stdout
- Parses JSON into local variable (named from context)
- Fields accessible via dot notation

**Example:**
```
CHECK: python3 lib/orchestration.py wait-explorers --required=3
# Binds: wait_result = {"status": "quorum_met", "completed": [...], "missing": [...]}
# Access: wait_result.status, wait_result.completed
```

### EMIT: Event Logging

```
EMIT: EVENT_TYPE key=value key2=value2
EMIT: "Human-readable message"
```

- Structured events use KEY=VALUE format
- Prose messages use quoted strings
- Events visible in orchestration logs

**Standard events:**
- `STATE_ENTRY state=X` — Entering state X
- `PHASE_TRANSITION from=X to=Y` — Moving between phases
- `TOOL_FAILURE tool=X error=Y` — Tool execution failed

### IF: Conditional Branching

```
IF: condition → action
```

- Evaluates condition using local/tracked variables
- Action can be: GOTO, EMIT, PROCEED, INCREMENT, compound

**Operators:**
- `==`, `!=` — Equality
- `>`, `<`, `>=`, `<=` — Comparison
- `AND`, `OR` — Boolean logic
- `is empty` — Collection check

**Examples:**
```
IF: wait_result.status == "quorum_met" → PROCEED
IF: iteration_count > 20 → EMIT: "Max reached", GOTO CASCADE
IF: ready_tasks is empty → GOTO CASCADE
IF: cascade.state == "stuck" AND len(cascade.unreachable) >= 2 → ...
```

### GOTO: State Transition

```
GOTO: STATE_NAME [with var=value]
```

- Jumps to named state
- Fresh context (locals reset, tracked persist)
- Optional context passing via `with`

### TRACK: Variable Declaration

```
TRACK: variable_name
```

- Declares persistent variable
- Initializes to 0 on first encounter
- No-op on subsequent encounters (preserves value)

### INCREMENT / SET: Variable Modification

```
INCREMENT: variable_name
SET: variable_name = expression
```

- `INCREMENT` adds 1 to tracked variable
- `SET` assigns expression result to tracked variable

### USE: Pattern Invocation

```
USE: PATTERN_NAME [with param=value, param2=value2]
```

- Invokes named pattern
- Substitutes parameters in pattern body
- Returns to caller after pattern completes

### WAIT: Blocking Condition

```
WAIT: condition OR timeout=Ns
```

- Blocks until condition true or timeout expires
- Typically wraps CHECK for polling

### PARALLEL: Concurrent Execution

```
DO: ... in PARALLEL
```

- Launches multiple operations concurrently
- Single message with multiple tool invocations
- All must complete before proceeding

---

## Pattern Parameter Binding

When invoking patterns with `USE:`, parameters substitute into pattern body:

| Pattern | Parameters | Substitution |
|---------|------------|--------------|
| INIT_PATTERN | `mode` | `{mode}` in EMIT statement |
| EXPLORE_PATTERN | `objective` | `{objective}` in explorer tasks |
| PLAN_PATTERN | `input`, `next_state` | `{input}` to planner, `GOTO {next_state}` |

**Example:**
```
# TASK flow
USE: EXPLORE_PATTERN with objective={task}
# Substitutes {task} for {objective} in explorer calls

# CAMPAIGN flow
USE: EXPLORE_PATTERN with objective={objective}
# Substitutes campaign objective
```

---

## State Machine Invariants

1. **Single active state** — Only one state executes at a time
2. **Tracked variables global** — Accessible from any state after declaration
3. **Local variables scoped** — Only valid within declaring state
4. **GOTO resets locals** — Fresh context on state entry
5. **RETURN exits machine** — Returns control to user with summary
