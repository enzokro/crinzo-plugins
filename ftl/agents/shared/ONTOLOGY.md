---
version: 1.1
---

# FTL Ontology

Single source of truth for core FTL concepts. All agents MUST reference this document for canonical definitions.

## Tool Budget

| Term | Definition |
|------|------------|
| `budget` | Total tool calls available to agent (set by Planner or workspace) |
| `budget_used` | Count of tool calls consumed so far |
| `budget_remaining` | `budget - budget_used` |

### Budget Accounting Rules

1. Each Read, Write, Edit, or Bash invocation = 1 tool call
2. EXEMPT: Preflight checks, workspace state transitions, memory operations
3. When `budget_remaining < 2` and verification fails → BLOCK

### EMIT Format

```
EMIT: "Budget: {budget_used}/{budget}, Action: {description}"
```

---

## BLOCK Status

| Attribute | Value |
|-----------|-------|
| Definition | Task unable to complete within constraints; requires discovery |
| Is Failure? | **NO** - Blocking is expected outcome for complex/novel tasks |
| Purpose | Informed handoff for Observer to extract learning |
| Trigger Conditions | Budget exhausted, idiom violation, error not in prior_knowledge, retry limit exceeded |

### BLOCK vs FAIL vs Error Pattern

| Term | Definition | Source | Learning? |
|------|------------|--------|-----------|
| **BLOCK** | Task unable to complete within constraints | Builder terminal state | Yes - Observer extracts |
| **FAIL** | Unexpected crash or system error | Exception, timeout | No |
| **Error Pattern** | Extracted learning from BLOCK event | Observer output | N/A - IS learning |

**Critical Distinction**: Observer extracts **Error Patterns** from **BLOCK** events. The term "failure" in `memory.py` refers to Error Patterns (prior knowledge), NOT to system failures. A BLOCK that yields a new Error Pattern is a successful learning event.

### BLOCK Report Format

```
Status: BLOCKED
Workspace: {path}
Reason: {error_summary}
Tried: {fixes_attempted}
Unknown: {unexpected_behavior}
Discovery: {what_observer_should_learn}
```

### Block Verification Status

| Status | Definition | Observer Action |
|--------|------------|-----------------|
| `CONFIRMED` | Re-ran verify command; still fails | Extract failure pattern |
| `FALSE_POSITIVE` | Re-ran verify command; now passes | Skip extraction (flaky) |

---

## EMIT Protocol

Structured event emission for observability and state machine tracking.

### Format

Two valid formats (machine-readable events vs human-readable status):

```
# Structured events (for state machine transitions):
EMIT: {EVENT_TYPE} key1=value1, key2=value2

# Status updates (for observability):
EMIT: "{Human-readable status string}"
```

### Event Types (Structured)

| Event | Required Keys | When |
|-------|---------------|------|
| `STATE_ENTRY` | `state` | Entering new state |
| `PHASE_TRANSITION` | `from`, `to` | Moving between phases |
| `DECISION` | `decision` | CLARIFY/PROCEED/CONFIRM |
| `PARTIAL_FAILURE` | `missing` | Timeout with quorum |
| `READY_TASKS` | `count`, `iteration` | Tasks available for execution |
| `CASCADE_PROPAGATE` | (none) | Block cascade triggered |

### Status Updates (Prose)

| Pattern | When |
|---------|------|
| `"Budget: {used}/{total}, Action: {desc}"` | After each tool call |
| `"Step: {name}, Status: {outcome}"` | Phase progress |
| `"Campaign complete. Workspaces: {N} complete, {M} blocked"` | Final summary |

### Example

```
EMIT: STATE_ENTRY state=BUILD
EMIT: "Budget: 2/5, Action: Read workspace record"
EMIT: PHASE_TRANSITION from=build to=observe
EMIT: "Step: complexity, Status: calculating C=18"
```

---

## Framework Confidence

Numeric score (0.0-1.0) indicating certainty of framework detection.

| Source | Explorer pattern mode |
|--------|----------------------|
| Range | 0.0 (uncertain) to 1.0 (certain) |
| Propagation | Explorer → Planner → Builder |

### Confidence Thresholds

| Score | Interpretation | Builder Behavior |
|-------|----------------|------------------|
| >= 0.6 | Sufficient confidence | Enforce idioms strictly (BLOCK on violation) |
| < 0.6 | Low confidence | Note idioms but don't BLOCK on violation |

**Rationale**: Two-tier system simplifies decision logic while maintaining safety. The 0.6 threshold balances false positives (blocking good code) against false negatives (allowing idiom violations).

### Propagation Chain

1. **Explorer (pattern mode)**: Detects framework, sets confidence
2. **Planner**: Includes confidence in plan.json idioms section
3. **Builder**: Reads confidence from workspace, adjusts enforcement

---

## Semantic Relevance

Score (0.0-1.0) indicating how well a memory entry matches current objective.

| Tier | Range | Injection Priority |
|------|-------|-------------------|
| Critical | >= 0.6 | Always inject |
| Productive | 0.4-0.6 | Inject if space |
| Exploration | 0.25-0.4 | Inject for discovery |
| Archive | < 0.25 | Don't inject |

---

## Workspace Lifecycle

```
Workspace ID format: {SEQ}_{slug}
Storage: workspace table in .ftl/ftl.db
Status tracking: workspace.status column (active|complete|blocked)
```

### Status Values

| Status | Meaning | Transitions To |
|--------|---------|----------------|
| `active` | Work in progress | `complete`, `blocked` |
| `complete` | Successfully finished | (terminal) |
| `blocked` | Unable to complete | (terminal) |

### Invariant

**Blocking is success** - It provides an informed handoff for Observer learning.

---

## Task Dependencies (DAG)

| Term | Definition |
|------|------------|
| `depends` | Task seq(s) that must complete before this task starts |
| `ready` | Task with `status=pending` AND all dependencies complete |
| `unreachable` | Task whose dependency is blocked (will be cascade-blocked) |

### Dependency Formats

```json
"depends": "none"           // No dependencies
"depends": "001"            // Single dependency
"depends": ["001", "002"]   // Multi-parent (DAG convergence)
```

---

## Memory Feedback Loop

Track whether injected memories helped or not.

| Field | Type | Purpose |
|-------|------|---------|
| `times_helped` | int | Count of successful utilizations |
| `times_failed` | int | Count of injected but unhelpful |
| `effectiveness` | float | `times_helped / (times_helped + times_failed)` |

### Effectiveness Impact

- Effective memories (high ratio): 1.5x importance weight
- Ineffective memories (low ratio): 0.5x importance weight
- Neutral (no feedback): 1.0x weight

---

## Vocabulary Disambiguation

Terms that appear across multiple contexts with different meanings:

| Term | Context | Meaning | Example Values |
|------|---------|---------|----------------|
| `wait_result` | orchestration.py | Explorer quorum outcome | `"quorum_met"`, `"timeout"`, `"all_complete"` |
| `decision` | decision_parser.py | Planner's output classification | `"PROCEED"`, `"CLARIFY"`, `"CONFIRM"`, `"UNKNOWN"` |
| `workspace_state` | workspace.py | Workspace lifecycle position | `"active"`, `"complete"`, `"blocked"` |
| `task_state` | campaign.py | Task execution status | `"pending"`, `"complete"`, `"blocked"`, `"stuck"` |
| `CONFIRM` | decision_parser.py | Planner wants user to select from options | Decision state in planning flow |
| `CONFIRMED` | observer.py | Block re-verified as genuine | Verification status after re-running verify command |

### CONFIRM vs CONFIRMED Disambiguation

These terms are related linguistically but represent distinct concepts:

| Term | Layer | Meaning | Used When |
|------|-------|---------|-----------|
| `CONFIRM` | Planning | Planner presents options; user must select | Ambiguous requirements with multiple valid approaches |
| `CONFIRMED` | Verification | Block verified as genuine (not false positive) | Observer re-ran verify command and it still fails |

**Mnemonic**: `CONFIRM` = asking for confirmation; `CONFIRMED` = verification completed (past tense).

**Avoid**: Using bare `status` without context. Always use the namespaced term in prose and variable names.

---

## Cross-References

| Document | Contains |
|----------|----------|
| [TOOL_BUDGET_REFERENCE.md](TOOL_BUDGET_REFERENCE.md) | Detailed budget rules |
| [FRAMEWORK_IDIOMS.md](FRAMEWORK_IDIOMS.md) | Framework detection & idioms |
| [ERROR_MATCHING_RULES.md](ERROR_MATCHING_RULES.md) | Error matching algorithm |
| [BUILDER_STATE_MACHINE.md](BUILDER_STATE_MACHINE.md) | Builder state transitions |
| [PLANNER_PHASES.md](PLANNER_PHASES.md) | Planner decision flow |
