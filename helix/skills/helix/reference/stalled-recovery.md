# STALLED Recovery (Orchestrator Judgment)

When build stalls (pending tasks but none ready), analyze the situation:

## Decision Table

| Condition | Action | Rationale |
|-----------|--------|-----------|
| Single blocked task, workaround exists | **SKIP** + store failure | Learn and continue; don't let peripheral work stop progress |
| Multiple tasks blocked by same root cause | **ABORT** + store systemic | Fundamental problem requires human insight |
| Blocked task is on critical path | **REPLAN** with narrower scope | Must solve it; try different decomposition |
| Blocking task has unclear verify | **REPLAN** with better verify | Specification was wrong, not implementation |
| 3+ attempts on same blocker | **ABORT** + escalate | I've tried; human needed |

## Command Flow

- **SKIP**: `TaskUpdate(task_id, status="completed", metadata={helix_outcome: "skipped", skip_reason: "..."})` -> continue build loop
- **REPLAN**: Start new PLAN phase with modified constraints
- **ABORT**: Summarize state, store learnings, end session
