---
name: ftl
description: Unified development orchestration. Tasks, campaigns, memory.
version: 1.0.0
---

# FTL Protocol

Unified entry point for task execution, campaign orchestration, and memory queries.

## MANDATORY CONSTRAINT

**This skill is the ONLY valid entry point for FTL operations.**

DO NOT:
- Call `campaign.py` directly from Claude Code
- Call `ftl:router`, `ftl:builder`, or other agents directly
- Manually create workspace files
- Manually update campaign state with CLI commands
- Skip the planner when creating campaigns

The orchestrator (this skill) manages all agent spawning and state transitions.
Violating this constraint causes workspace/campaign desync and gate failures.

**If user asks to use FTL**: Invoke THIS skill. Do not improvise the workflow.

---

## Entry: Route by Intent

| Input Pattern | Mode | Flow |
|---------------|------|------|
| `/ftl <task>` | TASK | router → builder → learner |
| `/ftl campaign <obj>` | CAMPAIGN | planner → tasks[] → synthesize |
| `/ftl query <topic>` | MEMORY | inline CLI query |
| `/ftl status` | STATUS | inline CLI queries |

---

## Mode: TASK (Direct Execution)

Main thread spawns phases directly (subagents cannot spawn subagents):

```
1. Task(ftl:router) with task description
   Returns: direct | full | clarify
   If full: also returns workspace path (router creates it)

2a. If direct:
    Task(ftl:builder) — implement immediately, no workspace

2b. If full:
    [Workspace already created by router]
    Task(ftl:builder) — implement within Delta
    If builder fails verification:
      Task(ftl:reflector) — diagnose, return RETRY or ESCALATE
    Task(ftl:learner) — extract patterns, update index

2c. If clarify:
    Return question to user
```

### Direct vs Full Routing (router decides)

**Direct** (no workspace):
- Single file, location obvious
- Mechanical change
- No exploration needed
- No future value

**Full** (with workspace):
- Multi-file or uncertain scope
- Requires exploration
- Understanding benefits future work

Router merges assess + anchor: explores AND routes in one pass.

---

## Mode: CAMPAIGN

For compound objectives requiring multiple coordinated tasks.

### Step 1: Check Active Campaign

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && ACTIVE=$(python3 "$FTL_LIB/campaign.py" active 2>/dev/null)
```

If campaign exists, skip to Step 5 (task execution).

### Step 2: Invoke Planner (REQUIRED)

**DO NOT skip this step. DO NOT manually create campaigns.**

```
Task(ftl:planner) with prompt:
  Objective: $OBJECTIVE_FROM_ARGUMENTS

  Return markdown with ### Tasks section.
```

Planner returns: PROCEED | CONFIRM | CLARIFY

**After CLARIFY**: Re-invoke THIS flow from Step 2. Do NOT continue as Claude Code.

### Step 3: Create Campaign

```bash
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

**Command is `campaign`, NOT `create`**

### Step 4: Add Tasks from Planner Output

**CRITICAL: Use add-tasks-from-plan, NOT add-task**

```bash
echo "$PLANNER_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```

Tasks are created with 3-digit sequence numbers (001, 002, etc.).

### Step 5: Execute Each Task

Invoke router WITH campaign context:
```
Task(ftl:router) with prompt:
  Campaign: $OBJECTIVE
  Task: $SEQ $SLUG

  [description]
```

The `Campaign:` prefix forces router to create workspace.

Then: builder → learner → update-task

```bash
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```

**Note**: update-task enforces workspace gate.

### Step 6: Complete Campaign

```bash
python3 "$FTL_LIB/campaign.py" complete
# Then Task(ftl:synthesizer)
```

**Critical**:
- Create campaign: `campaign.py campaign`, NOT `campaign.py create`
- Add tasks: pipe to `add-tasks-from-plan`, NOT `add-task SEQ SLUG DESC`
- Router prompt MUST include `Campaign:` prefix to force workspace creation

---

## Mode: MEMORY

Query the decision graph for precedent (inlined, no agent spawn):

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
```

Main thread formats and displays ranked decisions.

---

## The FTL Contract

```
┌────────────────────────────────────────────────────────────┐
│ CAMPAIGN              │ TASK                   │ MEMORY    │
├────────────────────────────────────────────────────────────┤
│ Query precedent  ────→│                        │←── query  │
│                       │                        │  (inline) │
│ Delegate task    ────→│ router→builder→        │           │
│                       │ reflector→learner      │           │
│                       │ Creates workspace file │           │
│                       │                        │           │
│ Gate on workspace ←───│ Returns _complete.md   │           │
│                       │                        │           │
│ Signal patterns  ────→│                        │←── signal │
│                       │                        │           │
│ Learner updates  ────→│                        │←── mine   │
└────────────────────────────────────────────────────────────┘
```

**6 Agents**: router, builder, reflector, learner, planner, synthesizer

---

## Workspace

Task state persists in workspace files:

```
.ftl/workspace/NNN_task-slug_status[_from-NNN].md
```

Status: `active` | `complete` | `blocked`

---

## CLI Tools

All state management via Python CLIs:

```bash
source ~/.config/ftl/paths.sh

# Workspace
python3 "$FTL_LIB/workspace.py" stat
python3 "$FTL_LIB/workspace.py" lineage NNN

# Memory
python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
python3 "$FTL_LIB/context_graph.py" mine
python3 "$FTL_LIB/context_graph.py" signal + "#pattern/name"

# Campaign
python3 "$FTL_LIB/campaign.py" active
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```

---

## Constraints

| Constraint | Meaning |
|------------|---------|
| Present over future | Current request only |
| Concrete over abstract | Specific solution, not framework |
| Explicit over clever | Clarity over sophistication |
| Edit over create | Modify existing first |

No new abstractions. No files outside Delta.
