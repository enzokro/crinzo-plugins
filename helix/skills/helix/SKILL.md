---
name: helix
description: Structured orchestrator with integrated memory. Spawns specialized agents for exploration, planning, building, and learning extraction.
argument-hint: Unless instructed otherwise, use the helix skill in all of your work
---

# Helix

Orchestration with memory-driven context injection and feedback-based learning.

**Architecture:**
```
Orchestrator State Machine (lib/orchestrator.py)
      ↓
INIT → EXPLORING → EXPLORED → PLANNING → PLANNED → BUILDING → BUILT → OBSERVING → DONE
                                             ↓
                                          STALLED → (replan | skip | abort)
      ↓
Native Claude Code Tasks (single source of truth)
      ↓
recall() ← injection → feedback_from_verification() → store()
```

Tasks are visible via Ctrl+T. Dependencies tracked natively. Parallel execution enabled.

## When to Use

- **Complex multi-step work** requiring exploration before implementation
- **Tasks that benefit from learned context** (similar work done before)
- **Work requiring verification** at each phase

For simple single-file changes, just do the work directly.

---

## Environment

Before running any helix commands, resolve the plugin path with fallback:
```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"
```
Use `$HELIX` in all subsequent commands. This handles both direct invocation and subagent spawning where environment variables may not propagate.

---

## State Machine

The orchestrator is implemented as an explicit state machine in `lib/orchestrator.py`.

### States

| State | Description |
|-------|-------------|
| INIT | Session start, ready to explore |
| EXPLORING | Explorer agent running |
| EXPLORED | Exploration complete, checkpoint saved |
| PLANNING | Planner agent running |
| PLANNED | Tasks created, checkpoint saved |
| BUILDING | Executing tasks (may be parallel) |
| STALLED | No ready tasks (blocked by blocked tasks) |
| BUILT | All tasks complete, checkpoint saved |
| OBSERVING | Observer extracting learning |
| DONE | Complete |
| ERROR | Unrecoverable error with typed reason |

### Transitions

```python
from lib.orchestrator import Orchestrator, State

orch = Orchestrator(objective="...")

# INIT -> EXPLORING
orch.transition("start")

# EXPLORING -> EXPLORED (guard: targets.files not empty)
result = orch.transition("exploration_complete", exploration_data)
if result.to_state == State.ERROR:
    handle_error(result.error_reason)  # ErrorReason.EMPTY_EXPLORATION

# EXPLORED -> PLANNING
orch.transition("start_planning")

# PLANNING -> PLANNED (guard: task_ids not empty, no cycles)
result = orch.transition("tasks_created", {
    "task_ids": [...],
    "task_mapping": {"001": "task-abc"},
    "dependencies": {"task-b": ["task-a"]}
})

# PLANNED -> BUILDING
orch.transition("start_building")

# BUILDING -> BUILDING (task loop)
orch.transition("task_complete", {"task_id": "task-abc", "status": "delivered"})

# Check for stall
is_stalled, stall_info = orch.check_stalled(all_tasks)
if is_stalled:
    orch.transition("stalled", stall_info)
    # User chooses: replan, skip, or abort

# BUILDING -> BUILT
orch.transition("all_complete")

# BUILT -> OBSERVING
orch.transition("start_observing")

# OBSERVING -> DONE
orch.transition("observation_complete")
```

### Error Reasons

| ErrorReason | Trigger | Recovery |
|-------------|---------|----------|
| EMPTY_EXPLORATION | No target files found | Re-explore with different query |
| NO_TASKS | Planner created no tasks | Re-plan with more context |
| CYCLES_DETECTED | Circular dependencies | Fix dependencies, re-plan |
| ALL_BLOCKED | All remaining tasks blocked | Replan, skip, or abort |
| VELOCITY_COLLAPSE | Tasks taking increasingly longer | Investigate systemic issue |
| SYSTEMIC_FAILURE | Same failure pattern 3+ times | Replan with failure context |
| INVALID_TRANSITION | Bug in orchestration logic | Check state machine |
| USER_ABORT | User chose to abort | Session ends |

### Checkpoints

Checkpoints are saved at significant state boundaries:
- `.helix/checkpoints/explored.json` - Exploration result
- `.helix/checkpoints/planned.json` - Task IDs and dependencies
- `.helix/checkpoints/built.json` - Completed and blocked tasks

Use `Orchestrator.resume(objective)` to restore from checkpoints.

---

## Phase 0: Session Recovery

```python
# Check for orphaned in-progress tasks
TaskList() → filter: status="in_progress"

if orphaned_tasks:
    # Present options to user via AskUserQuestion:
    # 1. Reset to pending - Resume these tasks
    # 2. Mark blocked - Skip these tasks
    # 3. Ignore - Start fresh (orphans remain)
```

---

## Phase 1: EXPLORE (Swarm Pattern)

**State:** INIT → EXPLORING → EXPLORED

**Architecture:** Orchestrator coordinates focused Haiku explorers. Orchestration stays in main conversation; explorers do scoped reconnaissance.

### Structure Discovery

Before spawning explorers, understand the codebase topology:

```bash
git ls-files | head -80   # If git repo: tracked files only, respects .gitignore
```

Alternative approaches depending on context:
- `find . -type f -name "*.py"` — when you need all files of a type
- `ls -R` — for shallow projects
- `tree -L 2` — for visual structure

**Goal:** See the natural divisions. Directories, modules, layers. Where is code dense? Where are boundaries?

### Partitioning Strategy

Partition the codebase for parallel exploration. Each explorer gets a bounded scope.

**Principles:**

1. **Follow natural boundaries** — Directories and modules are boundaries. `src/auth/` is coherent. `src/` is too broad.

2. **Top-down + Bottom-up** — Cover both directions:
   - *Top-down:* Where user intent enters (routes, CLI, handlers, config)
   - *Bottom-up:* Where primitives live (models, utils, core abstractions)

3. **Objective-relevant** — The user's goal determines focus. "Add authentication" → auth, middleware, users. "Fix database bug" → models, queries, migrations.

4. **Right granularity** — 3-6 explorers typically. Too few = unfocused. Too many = overhead.

5. **Always include:**
   - `memory` — Query learned failures and patterns
   - `framework` — Detect idioms and conventions

**Partitioning is judgment.** A FastAPI app might partition as: `api/`, `models/`, `core/`, `memory`, `framework`. A CLI tool might partition as: `commands/`, `lib/`, `config/`, `memory`, `framework`. Match the codebase's shape.

### Spawn Explorer Swarm

Launch explorers in parallel with focused prompts:

```
Task(
    subagent_type: "helix:helix-explorer",
    prompt: "SCOPE: {directory}\nFOCUS: {what to find}\nOBJECTIVE: {objective}",
    model: "haiku",
    run_in_background: true
)
```

Each explorer:
- Stays within its SCOPE
- Looks for what's relevant to FOCUS
- Returns `EXPLORER_FINDINGS:` JSON

### Collect and Synthesize

Collect all explorer outputs via `TaskOutput()`. Merge findings into a final, actionable and unified exploration:

```json
{
  "objective": "...",
  "structure": { "directories": [...], "entry_points": [...] },
  "patterns": { "framework": "...", "idioms": {...} },
  "memory": { "failures": [...], "patterns": [...] },
  "targets": { "files": [...], "details": [...] }
}
```

Synthesis this json file with active judgment: resolve conflicts, dedupe, identify what matters for the objective.

### Transition Guard

`exploration.targets.files` must not be empty. If empty → ERROR state.

Pass synthesized exploration to Planner.

---

## Phase 2: PLAN

**State:** EXPLORED → PLANNING → PLANNED

**Agent:** `helix:helix-planner` (opus)

**Contract:** See `agents/planner.yaml` for input/output schema.

**Spawn:**
```
Task(
    subagent_type: "helix:helix-planner",
    prompt: "OBJECTIVE: {objective}\nEXPLORATION: {exploration_results_json}",
    model: "opus"
)
```

**Transition guards:**
- `task_ids` must not be empty
- No cycles in dependencies

**Output:** Planner creates native Claude Code tasks with metadata:
```
TaskCreate(
    subject: "001: slug",
    description: "objective",
    activeForm: "Building slug",
    metadata: {delta, verify, budget, framework, idioms}
)
```

---

## Phase 3: BUILD

**State:** PLANNED → BUILDING → (BUILT | STALLED)

**Agent:** `helix:helix-builder` (opus, per task)

**Contract:** See `agents/builder.yaml` for input/output schema.

### Build Loop

```python
while pending_tasks_exist():
    ready_tasks = orch.get_ready_tasks(all_tasks)

    if not ready_tasks and pending_tasks_exist():
        is_stalled, info = orch.check_stalled(all_tasks)
        if is_stalled:
            orch.transition("stalled", info)
            # User decides: replan, skip, abort
            break

    for task in ready_tasks:
        # Build context
        context = build_context(task_data)

        # Store injected memories in task metadata
        TaskUpdate(task.id, metadata={
            ...existing,
            injected_memories: context["injected"]
        })

        # Spawn builder
        Task(
            subagent_type: "helix:helix-builder",
            prompt: context["prompt"],
            model: "opus",
            run_in_background: True  # Parallel execution
        )

    # Collect results
    for builder in running_builders:
        result = TaskOutput(builder.id)
        parsed = parse_output(result)

        # Close feedback loop via verification
        verify_cmd = task.metadata.verify
        verify_passed = run_command(verify_cmd).returncode == 0

        close_feedback_loop_verified(
            task_id=task.id,
            verify_passed=verify_passed,
            injected=task.metadata.injected_memories
        )

        orch.transition("task_complete", {
            "task_id": task.id,
            "status": parsed["status"]
        })
```

### Verification-Based Feedback

The learning loop uses **verification outcome** as ground truth, not builder self-report:

```python
# OLD (deprecated): Trust builder's UTILIZED report
close_feedback_loop(utilized=["mem1"], injected=["mem1", "mem2"])

# NEW: Use verification command result
verify_passed = subprocess.run(verify_cmd).returncode == 0
close_feedback_loop_verified(
    task_id=task_id,
    verify_passed=verify_passed,  # Ground truth
    injected=["mem1", "mem2"]
)
```

This prevents:
- Builder inflating by claiming all memories helped
- Builder deflating by claiming none helped
- Hallucinated memory names

---

## Phase 4: OBSERVE

**State:** BUILT → OBSERVING → DONE

**Agent:** `helix:helix-observer` (opus)

**Contract:** See `agents/observer.yaml` for input/output schema.

**Spawn:**
```
Task(
    subagent_type: "helix:helix-observer",
    prompt: "COMPLETED_TASK_IDS: {ids}\nPLUGIN_ROOT: {root}",
    model: "opus"
)
```

**Extracts:**
- **Failures** from blocked tasks (trigger + resolution)
- **Patterns** from successful tasks via SOAR chunking
- **Relationships** between memories (co_occurs, causes, solves)

---

## Memory System

### Scoring Formula

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)

effectiveness = helped / (helped + failed)  # default 0.5 if no feedback
recency = 2^(-days_since_use / 7)           # ACT-R decay
```

### Core Operations

```bash
# Store
python3 $HELIX/lib/memory/core.py store \
    --trigger "Situation description" \
    --resolution "What to do" \
    --type failure

# Recall
python3 $HELIX/lib/memory/core.py recall "query" --limit 5

# Feedback (verification-based, preferred)
python3 $HELIX/lib/memory/core.py feedback-verify \
    --task-id "task-abc" \
    --verify-passed true \
    --injected '["mem1", "mem2"]'

# Health
python3 $HELIX/lib/memory/core.py health
```

---

## Agent Contracts

Agents are defined by YAML contracts with input/output schemas:

```
agents/
├── explorer.yaml  # haiku, reconnaissance
├── planner.yaml   # opus, task decomposition
├── builder.yaml   # opus, task execution
└── observer.yaml  # opus, learning extraction
```

Load and validate:
```python
from lib.agents import AgentContract

contract = AgentContract("builder")
valid, error = contract.validate_input(task_data)
valid, error = contract.validate_output(result)
```

---

## CLI Commands

### Orchestrator
```bash
# Check current state
python3 $HELIX/lib/orchestrator.py status --objective "..."

# Clear checkpoints (start fresh)
python3 $HELIX/lib/orchestrator.py clear

# List valid transitions
python3 $HELIX/lib/orchestrator.py transitions
```

### Memory
```bash
python3 $HELIX/lib/memory/core.py health
python3 $HELIX/lib/memory/core.py recall "query"
python3 $HELIX/lib/memory/core.py consolidate
python3 $HELIX/lib/memory/core.py prune
```

### Tasks
```bash
python3 $HELIX/lib/tasks.py parse-output "$output"
python3 $HELIX/lib/tasks.py feedback-verify --task-id "..." --verify-passed true --injected '[...]'
python3 $HELIX/lib/tasks.py detect-cycles '{"a": ["b"], "b": ["a"]}'
```

---

## Integration Points

**Native Task system**:
- Tasks visible via Ctrl+T or /todos
- Status updates during execution
- Dependencies tracked via blockedBy
- Metadata stores delta/verify/budget/delivered/injected_memories

**PreToolUse hook** (`inject-context.py`):
- Triggers on Edit/Write
- Logs operations for debugging

**SessionStart hook** (`setup-env.sh`):
- Initializes database
- Sets environment variables
- Reports memory health

---

## Database

Single SQLite database at `.helix/helix.db`:

| Table | Purpose |
|-------|---------|
| memory | Failures and patterns with embeddings |
| memory_edge | Relationships between memories |
| exploration | Gathered context |

Checkpoints stored in `.helix/checkpoints/`.
