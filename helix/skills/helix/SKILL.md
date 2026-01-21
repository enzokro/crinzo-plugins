# Helix - Advanced Self-Learning Orchestrator

> Learning spirals upward. Each cycle builds on the last.

## Philosophy

Helix extends the core learning loop with sophisticated components:
- **Explorer**: Gathers context before planning
- **Planner**: Decomposes objectives into executable tasks
- **Builder**: Executes tasks with memory injection
- **Observer**: Extracts learning from outcomes

The memory system remains the persistence layer. The agents are the intelligence.

```
    ┌─────────────────────────────────────────────────────┐
    │                                                     │
    │   EXPLORE → PLAN → BUILD* → OBSERVE → FEEDBACK     │
    │      │                          │          │       │
    │      │         memories         │          │       │
    │      └──────────────────────────┴──────────┘       │
    │                                                     │
    │   * BUILD repeats for each task in the plan        │
    │                                                     │
    └─────────────────────────────────────────────────────┘
```

---

## Commands

| Command | Description |
|---------|-------------|
| `/helix <objective>` | Full pipeline: explore → plan → build → observe |
| `/helix:explore <objective>` | Just exploration (context gathering) |
| `/helix:plan` | Just planning (uses most recent exploration) |
| `/helix:query <text>` | Search memory by meaning |
| `/helix:stats` | Memory and learning statistics |
| `/helix:observe` | Extract learning from recent workspaces |

---

## Environment

```bash
PLUGIN_ROOT = <from .helix/plugin_root>
HELIX_DB_PATH = <optional: custom database path>
```

---

## State Machine

```
┌──────────┐
│   INIT   │
└────┬─────┘
     │
     ▼
┌──────────┐     ┌──────────┐
│ EXPLORE  │────▶│   PLAN   │
└──────────┘     └────┬─────┘
                      │
            ┌─────────┴─────────┐
            │                   │
            ▼                   ▼
     ┌──────────┐        ┌───────────┐
     │  CLARIFY │        │   BUILD   │◀─┐
     └──────────┘        └─────┬─────┘  │
                               │        │
                        ┌──────┴──────┐ │
                        │             │ │
                        ▼             ▼ │
                 ┌──────────┐  ┌──────────┐
                 │ COMPLETE │  │  NEXT    │──┘
                 └────┬─────┘  └──────────┘
                      │
                      ▼
               ┌──────────┐
               │ OBSERVE  │
               └────┬─────┘
                    │
                    ▼
               ┌──────────┐
               │ FEEDBACK │
               └────┬─────┘
                    │
                    ▼
               ┌──────────┐
               │   DONE   │
               └──────────┘
```

---

## INIT

Entry point. Determine command and route.

```yaml
ENTRY:
  DO: mkdir -p .helix
  DO: echo "$CLAUDE_PLUGIN_ROOT" > .helix/plugin_root

  CHECK: command type

  IF: /helix <objective>
    TRACK: OBJECTIVE = <objective>
    GOTO: EXPLORE

  IF: /helix:explore <objective>
    TRACK: OBJECTIVE = <objective>
    GOTO: EXPLORE
    # Stop after exploration

  IF: /helix:plan
    GOTO: PLAN
    # Uses most recent exploration

  IF: /helix:query <text>
    GOTO: QUERY

  IF: /helix:stats
    GOTO: STATS

  IF: /helix:observe
    GOTO: OBSERVE
```

---

## EXPLORE

Gather context for planning.

```yaml
STATE: EXPLORE
GOAL: Understand the codebase and task context

ACTIONS:
  # Launch explorer agent
  DO: Task(helix:helix-explorer)
      INPUT:
        OBJECTIVE: $OBJECTIVE
        PLUGIN_ROOT: $PLUGIN_ROOT
      CAPTURE: exploration_json

  # Parse explorer output
  PARSE: exploration_json for EXPLORATION_RESULT

  # Save exploration
  DO: echo '$exploration_json' | python3 $PLUGIN_ROOT/lib/exploration.py save
      CAPTURE: exploration_id

  OUTPUT: |
    ## Exploration Complete

    Structure: ${exploration.structure.directories}
    Framework: ${exploration.patterns.framework} (${exploration.patterns.framework_confidence})
    Failures loaded: ${len(exploration.memory.relevant_failures)}
    Patterns loaded: ${len(exploration.memory.relevant_patterns)}
    Target files: ${exploration.targets.files}

  IF: command was /helix:explore
    GOTO: DONE

  GOTO: PLAN
```

### Explorer Contract

The explorer outputs:
```json
{
  "objective": "...",
  "structure": {"directories": {}, "entry_points": [], ...},
  "patterns": {"framework": "...", "idioms": {...}},
  "memory": {"relevant_failures": [], "relevant_patterns": []},
  "targets": {"files": [], "functions": []}
}
```

---

## PLAN

Decompose objective into executable tasks.

```yaml
STATE: PLAN
GOAL: Create a task DAG for execution

ACTIONS:
  # Load most recent exploration
  DO: python3 $PLUGIN_ROOT/lib/exploration.py load
      CAPTURE: exploration

  # Launch planner agent
  DO: Task(helix:helix-planner)
      INPUT:
        OBJECTIVE: $OBJECTIVE
        EXPLORATION: $exploration
      CAPTURE: plan_json

  # Parse planner output
  PARSE: plan_json for PLAN_RESULT

  # Handle decision
  IF: plan.decision == "CLARIFY"
    TRACK: QUESTIONS = plan.questions
    GOTO: CLARIFY

  IF: plan.decision == "PROCEED"
    # Save plan
    DO: echo '$plan_json' | python3 $PLUGIN_ROOT/lib/plan.py save
        CAPTURE: plan_result

    IF: plan_result.error
      OUTPUT: "Plan error: ${plan_result.error}"
      GOTO: ERROR

    TRACK: PLAN_ID = plan_result.id
    TRACK: TASK_COUNT = plan_result.task_count

    OUTPUT: |
      ## Plan Created

      Tasks: $TASK_COUNT
      Framework: ${plan.framework}

      Task sequence:
      ${for task in plan.tasks: "${task.seq}: ${task.slug} [depends: ${task.depends}]"}

    GOTO: BUILD
```

### Planner Contract

The planner outputs:
```json
{
  "decision": "PROCEED|CLARIFY",
  "plan": {
    "objective": "...",
    "framework": "...",
    "idioms": {},
    "tasks": [{"seq", "slug", "objective", "delta", "verify", "depends", "budget"}]
  },
  "questions": []  // if CLARIFY
}
```

---

## CLARIFY

Handle planner's clarification request.

```yaml
STATE: CLARIFY
GOAL: Get missing information from user

ACTIONS:
  OUTPUT: |
    ## Clarification Needed

    The planner needs more information:

    ${for q in QUESTIONS: "- $q"}

    Please provide answers and run /helix again.

  GOTO: DONE
```

---

## BUILD

Execute tasks in dependency order.

```yaml
STATE: BUILD
GOAL: Execute ready tasks

ACTIONS:
  # Get ready tasks
  DO: python3 $PLUGIN_ROOT/lib/plan.py ready-tasks --plan-id $PLAN_ID
      CAPTURE: ready_tasks

  IF: ready_tasks is empty
    # Check cascade status
    DO: python3 $PLUGIN_ROOT/lib/plan.py cascade-status --plan-id $PLAN_ID
        CAPTURE: cascade

    IF: cascade.state == "complete"
      GOTO: COMPLETE

    IF: cascade.state == "stuck"
      OUTPUT: |
        ## Plan Stuck

        Unreachable tasks due to blocked dependencies:
        ${cascade.unreachable}

      GOTO: COMPLETE

    # Else all_blocked or in_progress (waiting)
    GOTO: COMPLETE

  # Execute each ready task
  FOR: task IN ready_tasks
    GOTO: BUILD_TASK with task

  # After all ready tasks complete, check for more
  GOTO: BUILD
```

---

## BUILD_TASK

Execute a single task.

```yaml
STATE: BUILD_TASK
GOAL: Execute one task with full context

ACTIONS:
  # Load plan for framework/idioms
  DO: python3 $PLUGIN_ROOT/lib/plan.py load --id $PLAN_ID
      CAPTURE: plan

  # Create workspace with memory injection
  DO: python3 $PLUGIN_ROOT/lib/workspace.py create \
        --plan-id $PLAN_ID \
        --task '${json(task)}' \
        --framework '${plan.framework}' \
        --idioms '${json(plan.idioms)}'
      CAPTURE: workspace

  OUTPUT: |
    ### Building: ${task.seq} - ${task.slug}

    Objective: ${task.objective}
    Delta: ${task.delta}
    Budget: ${task.budget}
    Injected memories: ${len(workspace.failures) + len(workspace.patterns)}

  # Launch builder agent
  DO: Task(helix:helix-builder)
      INPUT:
        WORKSPACE: $workspace
      CAPTURE: builder_output

  # Parse builder output
  PARSE: builder_output for DELIVERED or BLOCKED

  IF: DELIVERED found
    # Extract utilized memories
    PARSE: builder_output for UTILIZED

    # Complete workspace
    DO: python3 $PLUGIN_ROOT/lib/workspace.py complete \
          --id ${workspace._id} \
          --delivered "$DELIVERED" \
          --utilized '${json(UTILIZED)}'

    OUTPUT: "✓ ${task.seq}: $DELIVERED"

  IF: BLOCKED found
    # Extract reason and any utilized
    PARSE: builder_output for BLOCKED reason
    PARSE: builder_output for UTILIZED (may be empty)

    # Block workspace
    DO: python3 $PLUGIN_ROOT/lib/workspace.py block \
          --id ${workspace._id} \
          --reason "$BLOCKED" \
          --utilized '${json(UTILIZED)}'

    OUTPUT: "✗ ${task.seq}: BLOCKED - $BLOCKED"

  RETURN: to BUILD loop
```

---

## COMPLETE

All tasks processed. Summarize and proceed to observation.

```yaml
STATE: COMPLETE
GOAL: Summarize build results

ACTIONS:
  DO: python3 $PLUGIN_ROOT/lib/workspace.py list --plan-id $PLAN_ID
      CAPTURE: workspaces

  TRACK: complete_count = count where status == "complete"
  TRACK: blocked_count = count where status == "blocked"

  OUTPUT: |
    ## Build Complete

    ✓ Completed: $complete_count
    ✗ Blocked: $blocked_count

    ${for ws in workspaces: "${ws.task_seq}: ${ws.status} - ${ws.delivered[:50]}..."}

  GOTO: OBSERVE
```

---

## OBSERVE

Extract learning from completed work.

```yaml
STATE: OBSERVE
GOAL: Extract failures and patterns for future use

ACTIONS:
  # Get workspaces for observation
  DO: python3 $PLUGIN_ROOT/lib/workspace.py list --plan-id $PLAN_ID
      CAPTURE: workspaces

  # Launch observer agent
  DO: Task(helix:helix-observer)
      INPUT:
        WORKSPACES: $workspaces
        PLUGIN_ROOT: $PLUGIN_ROOT
      CAPTURE: observer_output

  # Parse observer output
  PARSE: observer_output for OBSERVATION_RESULT

  OUTPUT: |
    ## Learning Extracted

    Analyzed: ${observation.analyzed.complete} complete, ${observation.analyzed.blocked} blocked

    New failures: ${len(observation.extracted.failures)}
    ${for f in observation.extracted.failures: "  - ${f.name}: ${f.trigger[:40]}..."}

    New patterns: ${len(observation.extracted.patterns)}
    ${for p in observation.extracted.patterns: "  - ${p.name}: ${p.trigger[:40]}..."}

    Relationships: ${len(observation.extracted.relationships)}

  GOTO: FEEDBACK
```

---

## FEEDBACK

Verify the learning loop is closed.

```yaml
STATE: FEEDBACK
GOAL: Verify learning loop closure

ACTIONS:
  DO: python3 $PLUGIN_ROOT/lib/memory.py verify
      CAPTURE: verify_result

  OUTPUT: |
    ## Learning Loop: ${verify_result.status}

    Memories: ${verify_result.stats.total}
    With feedback: ${verify_result.stats.with_feedback}
    Overall effectiveness: ${verify_result.stats.overall_effectiveness}

    ${if verify_result.issues: "Issues:"}
    ${for issue in verify_result.issues: "  - $issue"}

  # Mark plan complete
  DO: python3 $PLUGIN_ROOT/lib/plan.py complete --plan-id $PLAN_ID

  GOTO: DONE
```

---

## QUERY

Search memory by meaning.

```yaml
STATE: QUERY
GOAL: Find relevant memories

ACTIONS:
  DO: python3 $PLUGIN_ROOT/lib/memory.py query "$QUERY_TEXT" --limit 10
      CAPTURE: results

  OUTPUT: |
    ## Memory Search: "$QUERY_TEXT"

    ${for m in results:}
    **${m.name}** (${m.type}, effectiveness: ${m.effectiveness})
    - Trigger: ${m.trigger}
    - Resolution: ${m.resolution}
    - Relevance: ${m._relevance}
    ${endfor}

  GOTO: DONE
```

---

## STATS

Display memory statistics.

```yaml
STATE: STATS
GOAL: Show learning system health

ACTIONS:
  DO: python3 $PLUGIN_ROOT/lib/memory.py stats
      CAPTURE: stats

  DO: python3 $PLUGIN_ROOT/lib/memory.py verify
      CAPTURE: verify

  OUTPUT: |
    ## Helix Memory Statistics

    **Total memories**: ${stats.total}
    - Failures: ${stats.by_type.failure.count if 'failure' in stats.by_type else 0}
    - Patterns: ${stats.by_type.pattern.count if 'pattern' in stats.by_type else 0}

    **Effectiveness**
    - Overall: ${stats.overall_effectiveness}
    - Total helped: ${stats.total_helped}
    - Total failed: ${stats.total_failed}

    **Feedback Loop**
    - With feedback: ${stats.with_feedback}
    - Without feedback: ${stats.without_feedback}

    **Graph**
    - Relationships: ${stats.relationships}
    - Embedding coverage: ${stats.embedding_coverage}

    **Loop Status**: ${verify.status}
    ${for issue in verify.issues: "  ⚠ $issue"}

  GOTO: DONE
```

---

## DONE

Terminal state.

```yaml
STATE: DONE
GOAL: Clean exit

ACTIONS:
  # Nothing to do - orchestration complete
```

---

## ERROR

Error handling state.

```yaml
STATE: ERROR
GOAL: Handle errors gracefully

ACTIONS:
  OUTPUT: |
    ## Error Occurred

    ${ERROR_MESSAGE}

    Memory state preserved. Run /helix:stats to check health.

  GOTO: DONE
```

---

## The Learning Spiral

```
    Session 1:
    ┌──────────────────────────────────────────┐
    │ EXPLORE → PLAN → BUILD → OBSERVE         │
    │                              │            │
    │                              ▼            │
    │                         [memories]        │
    └──────────────────────────────────────────┘
                                   │
                                   ▼
    Session 2:
    ┌──────────────────────────────────────────┐
    │ EXPLORE ────────────────────┐            │
    │    │                        │            │
    │    │    [memories injected] │            │
    │    ▼                        │            │
    │  PLAN → BUILD → OBSERVE ────┘            │
    │              │                           │
    │              ▼                           │
    │         [more memories]                  │
    │         [feedback updates]               │
    └──────────────────────────────────────────┘
                                   │
                                   ▼
    Session N:
    ┌──────────────────────────────────────────┐
    │  Accumulated knowledge makes             │
    │  exploration richer, planning smarter,   │
    │  building more reliable.                 │
    │                                          │
    │  The spiral ascends.                     │
    └──────────────────────────────────────────┘
```

Each session:
1. Benefits from previous sessions' memories
2. Contributes new memories for future sessions
3. Feedback adjusts memory rankings
4. Ineffective memories fade, effective ones rise

**This is how learning compounds.**
