---
name: helix
description: Structured orchestrator with integrated memory. Spawns specialized agents for exploration, planning, building, and learning extraction.
argument-hint: <objective>
---

# Helix

Orchestration with memory-driven context injection and feedback-based learning.

**Architecture:**
```
Native Claude Code Tasks ← Single source of truth
      ↓
EXPLORE → PLAN → BUILD → OBSERVE
    ↓         ↓        ↓        ↓
recall() → TaskCreate → feedback() → store()
```

Tasks are visible via Ctrl+T. Dependencies tracked natively. Parallel execution enabled.

## When to Use

- **Complex multi-step work** requiring exploration before implementation
- **Tasks that benefit from learned context** (similar work done before)
- **Work requiring verification** at each phase

For simple single-file changes, just do the work directly.

---

## Phase 1: EXPLORE

**Purpose:** Gather codebase context before planning.

**Agent:** `helix:helix-explorer` (haiku, 6 tool budget)

**Spawn:**
```
Task(
    subagent_type: "helix:helix-explorer",
    prompt: """
OBJECTIVE: {objective}
PLUGIN_ROOT: {$HELIX_PLUGIN_ROOT}

Explore the codebase and output EXPLORATION_RESULT JSON.
""",
    model: "haiku"
)
```

**Output:** JSON with structure, patterns, memory, targets.

---

## Phase 2: PLAN

**Purpose:** Decompose objective into executable task DAG using native Tasks.

**Agent:** `helix:helix-planner` (opus)

**Spawn:**
```
Task(
    subagent_type: "helix:helix-planner",
    prompt: """
OBJECTIVE: {objective}

EXPLORATION:
{exploration_json}

Create tasks using TaskCreate with metadata containing delta, verify, budget.
Set dependencies using TaskUpdate with addBlockedBy.
Output TASK_MAPPING and PLAN_COMPLETE.
""",
    model: "opus"
)
```

**Output:** Planner creates native Claude Code tasks with metadata:
```
TaskCreate(
    subject: "001: slug",
    description: "objective",
    activeForm: "Building slug",
    metadata: {delta, verify, budget, framework, idioms}
)
```

**Parse mapping:**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/tasks.py extract-mapping "$planner_output"
```

**Decision points:**
- `PLAN_COMPLETE` - tasks created, proceed to build
- `CLARIFY` - need answers before proceeding

---

## Phase 3: BUILD (Parallel Execution)

**Purpose:** Execute tasks in dependency order with parallel execution.

### Build Loop

```
while pending tasks exist:
    # 1. Get ready tasks using TaskList
    TaskList() → filter: status="pending" AND blockedBy=[]

    # 2. For each ready task (can be parallel):
    for task in ready_tasks:
        # Get full context
        task_data = TaskGet(task.id)

        # Build lineage from completed blockers
        lineage = []
        for blocker_id in completed_blockers:
            blocker = TaskGet(blocker_id)
            lineage.append({
                seq: blocker.subject.split(":")[0],
                slug: blocker.subject.split(":")[1],
                delivered: blocker.metadata.delivered
            })

        # Build prompt with memory injection
        prompt = python3 $HELIX_PLUGIN_ROOT/lib/context.py build-prompt \
            --task-data '${task_data_json}' \
            --lineage '${lineage_json}'

        # Mark in progress and claim
        TaskUpdate(task.id, owner="helix-builder", status="in_progress")

        # Spawn builder (parallel if multiple ready)
        Task(
            subagent_type: "helix:helix-builder",
            prompt: prompt,
            model: "opus",
            run_in_background: true  # Enable parallelism
        )

    # 3. Poll for completions
    for background_task in running_builders:
        result = TaskOutput(task_id=background_task.id, block=true)

        # Parse output
        parsed = python3 $HELIX_PLUGIN_ROOT/lib/tasks.py parse-output "$result"

        # Update task metadata with results
        TaskUpdate(task.id, status="completed", metadata={
            ...existing_metadata,
            delivered: parsed.summary,
            utilized: parsed.utilized
        })

        # Close feedback loop IMMEDIATELY (per-task, not batched)
        injected = python3 $HELIX_PLUGIN_ROOT/lib/context.py get-injected \
            --objective "${task_objective}"

        python3 $HELIX_PLUGIN_ROOT/lib/tasks.py feedback \
            --utilized '${parsed.utilized}' \
            --injected '${injected}'
```

### Parallel Execution Rules

1. **Independent tasks**: If tasks A, B, C have no dependencies between them, spawn all 3 with `run_in_background: true`
2. **Dependent tasks**: Task D blocked by A cannot start until A completes
3. **Learning preserved**: Feedback called per-task on completion, not batched
4. **Owner tracking**: Each builder claims its task via owner field

### Context Building

For each task, the prompt includes:
```
TASK: {subject}
OBJECTIVE: {description}
DELTA: {metadata.delta}
VERIFY: {metadata.verify}
BUDGET: {metadata.budget}
FRAMEWORK: {metadata.framework}
IDIOMS: {metadata.idioms}
FAILURES_TO_AVOID: {recalled failures}
PATTERNS_TO_APPLY: {recalled patterns}
INJECTED_MEMORIES: {memory names for feedback tracking}
PARENT_DELIVERIES: {lineage from completed blockers}
```

### Handling Blocks

If a builder reports BLOCKED:
- Task is marked completed with delivered="BLOCKED: reason"
- Downstream tasks remain blocked (can't start)
- Observer will analyze for learning extraction
- Consider: replan, skip, or escalate to user

---

## Phase 4: OBSERVE

**Purpose:** Extract learning from completed work.

**Agent:** `helix:helix-observer` (opus)

**Spawn:**
```
Task(
    subagent_type: "helix:helix-observer",
    prompt: """
COMPLETED_TASK_IDS: {list of completed task ids}
PLUGIN_ROOT: {$HELIX_PLUGIN_ROOT}

For each task ID, use TaskGet to retrieve results.
Extract failures and patterns. Store to memory.
Output OBSERVATION_RESULT.
""",
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

Memories that help rise in ranking. Memories that don't help sink.

### Core Operations

**Store:**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py store \
    --trigger "Situation description" \
    --resolution "What to do" \
    --type failure  # or pattern
```

**Recall:**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py recall "query" --limit 5
```

**Feedback:**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py feedback \
    --utilized '["mem-1"]' \
    --injected '["mem-1", "mem-2"]'
```

**Chunk (SOAR pattern extraction):**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py chunk \
    --task "Task objective" \
    --outcome "success" \
    --approach "Technique used"
```

**Health:**
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py health
```

### Maintenance Operations

**Consolidate** - merge similar memories:
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py consolidate
```

**Prune** - remove ineffective memories:
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py prune
```

**Decay** - find dormant memories:
```bash
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py decay
```

---

## Cognitive Guidelines

### Before Acting

1. **Query memory first** - check for relevant failures and patterns
2. **Assess complexity** - simple tasks don't need orchestration
3. **Understand intent** - what does success actually look like?

### During Execution

1. **Stay in scope** - delta is a hard constraint
2. **Verify before claiming success** - run the verify command
3. **Block when stuck** - clear blocking info > broken code

### Reporting

**UTILIZED must be accurate.** Only report memories you actually applied:
```
UTILIZED:
- memory-name: Applied validation pattern from resolution
```

Not:
```
UTILIZED: memory-1, memory-2, memory-3  # listing everything injected
```

False positives corrupt the feedback signal.

---

## Database

Single SQLite database at `.helix/helix.db`:

| Table | Purpose |
|-------|---------|
| memory | Failures and patterns with embeddings |
| memory_edge | Relationships between memories |
| exploration | Gathered context |

Note: Plans and workspaces are now handled by Claude Code's native Task system with metadata.

---

## Integration Points

**Native Task system**:
- Tasks visible via Ctrl+T or /todos
- Status updates during execution
- Dependencies tracked via blockedBy
- Metadata stores delta/verify/budget/delivered/utilized
- Owner field tracks which agent claimed the task

**PreToolUse hook** (`inject-context.py`):
- Triggers on Edit/Write
- Injects relevant memories
- Requests UTILIZED reporting

**SessionStart hook** (`setup-env.sh`):
- Initializes database
- Sets environment variables
- Reports memory health

---

## New Capabilities

1. **Parallel Builders**: Use `run_in_background: true` for independent tasks
2. **Cross-Session Persistence**: Set `CLAUDE_CODE_TASK_LIST_ID` for long projects
3. **Agent Claim Tracking**: `owner` field prevents task collision
4. **Native Task Visibility**: Users see helix tasks in Ctrl+T
5. **Background Monitoring**: `TaskOutput` for swarm status polling
