# Error Handling

Consolidated error taxonomy, recovery strategies, and the ERROR state protocol.

---

## Error Taxonomy

### Transient Errors

Temporary failures that may resolve on retry.

| Error | Example | Recovery |
|-------|---------|----------|
| Network timeout | Explorer HTTP timeout | Retry once |
| Rate limiting | API throttle | Wait + retry |
| Resource contention | File lock held | Brief pause + retry |
| Flaky test | Intermittent test failure | Retry up to 2x |

**Characteristics:**
- Non-deterministic
- Often self-resolving
- Safe to retry

### Structural Errors

Fundamental problems requiring different approach.

| Error | Example | Recovery |
|-------|---------|----------|
| Schema mismatch | Invalid JSON structure | Validate before use |
| Missing dependency | Import not found | GOTO ERROR |
| Invalid state | Unexpected task_state | GOTO ERROR |
| Cycle detected | DAG has cycle | Reject plan |
| Budget exhausted | Builder out of tools | BLOCK workspace |

**Characteristics:**
- Deterministic
- Won't resolve on retry
- Require state machine handling

---

## Error State Protocol

When ANY FTL CLI tool fails:

### Step 1: Emit the Error

```
EMIT: TOOL_FAILURE tool={name} error={message}
```

Always log the failure before attempting recovery.

### Step 2: Classify the Error

**Transient?**
- Timeout, network, rate limit → Retry once
- If retry fails → Treat as structural

**Structural?**
- ValueError, schema mismatch → Attempt in-state recovery
- If unrecoverable → `GOTO ERROR`

### Step 3: Attempt Recovery

**For transient errors:**
```
IF: error is transient → retry once
IF: retry fails → treat as structural
```

**For structural errors:**
```
EMIT: STATE_ENTRY state=ERROR error_type={type}
# Attempt recovery WITHIN state machine:
#   - For workspace creation: use manual workspace record generation
#   - For plan parsing: validate JSON schema before use
IF: unrecoverable → GOTO ERROR with context
```

### Step 4: Never Break Protocol

```
5. NEVER "break out" to independent operation
   - All recovery flows through states
   - No ad-hoc tool execution outside state context
   - If tempted to bypass, EMIT first and document rationale
```

---

## ERROR_PATTERN

The canonical error handling implementation.

```
STATE: ERROR
  EMIT: STATE_ENTRY state=ERROR error_type={type}

  IF: error_type=="timeout" →
      EMIT: "Exploration timeout, using partial data"
      GOTO PLAN

  IF: error_type=="quorum_failure" →
      EMIT: "Insufficient explorer data"
      RETURN with partial results

  IF: error_type=="cascade_stuck" →
      DO: python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-analysis
      RETURN with analysis

  IF: error_type=="schema_invalid" →
      EMIT: "Invalid schema, cannot proceed"
      RETURN with schema errors

  IF: error_type=="budget_exhausted" →
      EMIT: "Builder budget exhausted"
      # Workspace should already be blocked
      GOTO OBSERVE

  DEFAULT:
      EMIT: "Unrecoverable error: {type}"
      RETURN with error summary
```

---

## Error Type Reference

### Exploration Errors

| Type | Trigger | Recovery |
|------|---------|----------|
| `timeout` | Explorer didn't complete in 300s | Use partial data, proceed to PLAN |
| `quorum_failure` | <3 explorers completed | RETURN with partial results |
| `aggregation_failed` | exploration.py aggregate error | Retry aggregation, then ERROR |

### Planning Errors

| Type | Trigger | Recovery |
|------|---------|----------|
| `clarify_exhausted` | 5+ clarification rounds | RETURN with questions summary |
| `decision_unknown` | Planner output unparseable | Default to CLARIFY |
| `schema_invalid` | plan.json doesn't match schema | RETURN with validation errors |
| `cycle_detected` | DAG has circular dependencies | Reject plan, request revision |

### Build Errors

| Type | Trigger | Recovery |
|------|---------|----------|
| `budget_exhausted` | Builder used all tool calls | BLOCK workspace |
| `verify_failed` | Tests fail after retries | BLOCK workspace |
| `idiom_violation` | Code violates framework idioms | BLOCK workspace |
| `workspace_invalid` | Malformed workspace record | Regenerate workspace |

### Campaign Errors

| Type | Trigger | Recovery |
|------|---------|----------|
| `cascade_stuck` | Unreachable tasks >= 2 | Attempt replan or propagate blocks |
| `iteration_exhausted` | 20+ execute iterations | Force CASCADE state |
| `stuck_detected` | ready_tasks unchanged 3+ iterations | Force CASCADE state |

---

## Error Recovery Decision Tree

```
Error Occurred
     │
     ├─ Is it transient?
     │       │
     │       ├─ Yes → Retry once
     │       │         │
     │       │         ├─ Success → Continue
     │       │         └─ Fail → Treat as structural
     │       │
     │       └─ No → Structural error
     │
     └─ Structural error
             │
             ├─ Can recover in-state?
             │       │
             │       ├─ Yes → Apply recovery strategy
             │       │         │
             │       │         ├─ Success → Continue
             │       │         └─ Fail → GOTO ERROR
             │       │
             │       └─ No → GOTO ERROR immediately
             │
             └─ In ERROR state
                     │
                     ├─ Known error_type → Apply ERROR_PATTERN handler
                     │
                     └─ Unknown → RETURN with error summary
```

---

## State-Specific Recovery

### EXPLORE State

```
Error: Explorer timeout
Recovery:
  - Check quorum (3+ complete?)
  - If quorum met: proceed with partial data
  - If quorum failed: GOTO ERROR with error_type="quorum_failure"
```

### PLAN State

```
Error: Decision parsing failed
Recovery:
  - Validate plan_output.md exists
  - Check for JSON block in output
  - If parseable: extract and continue
  - If unparseable: default to CLARIFY, increment counter
```

### BUILD State

```
Error: Workspace creation failed (ValueError)
Recovery:
  - Check target_lines format
  - If non-numeric: fallback to default context extraction
  - If structural: regenerate workspace with minimal context
  - If unrecoverable: BLOCK workspace
```

### EXECUTE State

```
Error: Task update failed
Recovery:
  - Verify workspace exists
  - Check task_state transition validity
  - If valid: retry update
  - If invalid: log and continue (task already transitioned)
```

---

## Error Logging Format

Standard EMIT format for errors:

```
EMIT: TOOL_FAILURE tool={tool_name} error={error_message}
EMIT: STATE_ENTRY state=ERROR error_type={type}
EMIT: RECOVERY_ATTEMPT strategy={strategy} success={true|false}
```

**Examples:**
```
EMIT: TOOL_FAILURE tool=workspace.py error="ValueError: invalid literal for int()"
EMIT: STATE_ENTRY state=ERROR error_type=schema_invalid
EMIT: RECOVERY_ATTEMPT strategy=fallback_context success=true
```

---

## Critical Invariants

1. **Emit before recovery** — Always log the error first
2. **Classify before acting** — Distinguish transient vs structural
3. **Stay in state machine** — No independent operation
4. **One retry for transient** — Don't retry structural errors
5. **ERROR is a state** — Not manual intervention
6. **RETURN is valid** — Graceful exit with summary is acceptable
