---
description: Unified development orchestration. Tasks, campaigns, memory.
allowed-tools: Task, Read, Glob, Bash
---

# FTL - Unified Entry Point

Route by intent. One command for all FTL capabilities.

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

## Routing Logic

Parse `$ARGUMENTS` to determine mode:

### 1. Campaign Mode
If arguments start with `campaign `:
```
/ftl campaign add OAuth integration
```
→ Invoke `ftl:planner` for campaign planning

### 2. Query Mode
If arguments start with `query `:
```
/ftl query auth patterns
```
→ Inline: query context_graph, format results

### 3. Status Mode
If arguments equal `status`:
```
/ftl status
```
→ Inline: combined status (campaign + workspace + lattice + scout)

### 4. Task Mode (Default)
Any other input is a direct task:
```
/ftl fix the login bug
/ftl add validation to the form
```
→ Invoke `ftl:router` for routing, then execute

## Execution Protocol

### Task Mode Flow

1. **Router** (route + explore + anchor):
```
Task tool with subagent_type: ftl:router
Prompt: $ARGUMENTS
```
Returns: `direct` | `full` | `clarify`
If full: also returns workspace path (router creates it)

2a. **If direct** (simple task):
```
Task tool with subagent_type: ftl:builder
Prompt: |
  Task: $ARGUMENTS
  [No workspace — direct execution]
```

2b. **If full** (needs workspace):
```
Task tool with subagent_type: ftl:builder
Prompt: |
  Workspace: $WORKSPACE_PATH
```

If builder fails verification:
```
Task tool with subagent_type: ftl:reflector
Prompt: |
  Workspace: $WORKSPACE_PATH
  Failure: [verification output]
```
Returns: RETRY (with strategy) or ESCALATE (with diagnosis)

After completion:
```
Task tool with subagent_type: ftl:learner
Prompt: |
  Workspace: $WORKSPACE_PATH
```

2c. **If clarify**:
Return question to user, halt.

### Campaign Mode Flow

#### Step 1: Check for Active Campaign

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && ACTIVE=$(python3 "$FTL_LIB/campaign.py" active 2>/dev/null)
```

If campaign exists, skip to Step 5 (task execution).

#### Step 2: Invoke Planner (REQUIRED)

**DO NOT skip this step. DO NOT manually create campaigns.**

```
Task tool with subagent_type: ftl:planner
Prompt: |
  Objective: $OBJECTIVE_FROM_ARGUMENTS

  Plan campaign with verification-first decomposition.
  Return markdown with ### Tasks section in this exact format:

  ### Tasks
  1. **slug**: description
     Delta: specific/files.ts
     Depends: none
     Done when: observable outcome
     Verify: command
```

Wait for planner response. Planner returns one of:
- **PROCEED**: Clear plan, continue to Step 3
- **CONFIRM**: Show plan to user, await approval, then Step 3
- **CLARIFY**: Return questions to user, HALT

**CRITICAL - After CLARIFY**:
When user answers, you MUST re-invoke THIS campaign flow from Step 2.
Do NOT continue as Claude Code. Do NOT improvise.
Re-invoke planner with: `Objective: $OBJECTIVE\n\nUser clarified: $USER_RESPONSE`

#### Step 3: Create Campaign

Store planner's full response for piping:
```bash
PLAN_OUTPUT="[full planner response including ### Tasks section]"
```

Create campaign file (**command is `campaign`, NOT `create`**):
```bash
source ~/.config/ftl/paths.sh 2>/dev/null && python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

#### Step 4: Add Tasks from Planner Output

**CRITICAL: Use add-tasks-from-plan, NOT add-task**

```bash
echo "$PLAN_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```

This parses the planner's markdown and creates all tasks with 3-digit sequence numbers (001, 002, etc.).

**DO NOT** call `add-task` individually. It lacks description context.

#### Step 5: Execute Each Task

For each pending task:

```bash
# Get next pending task
TASK_INFO=$(python3 "$FTL_LIB/campaign.py" pending | head -1)
SEQ=$(echo "$TASK_INFO" | cut -d'_' -f1)
SLUG=$(echo "$TASK_INFO" | cut -d'_' -f2)
```

Invoke router WITH campaign context (forces `full` routing):
```
Task tool with subagent_type: ftl:router
Prompt: |
  Campaign: $OBJECTIVE
  Task: $SEQ $SLUG

  [task description from planner output]
```

The `Campaign:` prefix forces router to:
- Route `full` (not `direct`)
- Create workspace file in `.ftl/workspace/`
- Return workspace path

After router returns, invoke builder:
```
Task tool with subagent_type: ftl:builder
Prompt: |
  Workspace: $WORKSPACE_PATH
```

After builder completes, invoke learner:
```
Task tool with subagent_type: ftl:learner
Prompt: |
  Workspace: $WORKSPACE_PATH
```

Then update task status (seq is already 3-digit from add-tasks-from-plan):
```bash
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```

**Note**: update-task enforces workspace gate. It will fail if no `{SEQ}_*_complete*.md` file exists.

Repeat Step 5 for all pending tasks.

#### Step 6: Complete Campaign

When all tasks complete:
```bash
python3 "$FTL_LIB/campaign.py" complete
```

Then invoke synthesizer:
```
Task tool with subagent_type: ftl:synthesizer
```

### Query Mode Flow (Inlined)

No agent spawn. Main thread executes:

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
```

Format and display ranked decisions with Path, Delta, Tags, and Traces excerpt.

### Status Mode Flow (Inlined)

No agent spawn. Main thread executes:

```bash
source ~/.config/ftl/paths.sh 2>/dev/null

# Campaign status
python3 "$FTL_LIB/campaign.py" status

# Workspace status
python3 "$FTL_LIB/workspace.py" stat

# Scout queries (opportunities)
python3 "$FTL_LIB/campaign.py" active
python3 "$FTL_LIB/context_graph.py" age 30
```

Format and display combined status with opportunities.

## Examples

```
/ftl fix typo in README                    → Task mode (direct)
/ftl add user authentication               → Task mode (full)
/ftl campaign implement OAuth with Google  → Campaign mode
/ftl query session handling                → Query mode (inline)
/ftl status                                → Status mode (inline)
```

## Constraint

Main thread spawns phases directly. Subagents cannot spawn other subagents.

**6 Agents**: router, builder, reflector, learner, planner, synthesizer
