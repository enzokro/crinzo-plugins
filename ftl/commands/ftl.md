---
description: Unified development orchestration. Tasks, campaigns, memory.
allowed-tools: Task, Read, Glob, Bash
---

# FTL - Unified Entry Point

Route by intent. One command for all FTL capabilities.

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

1. Check active campaign:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/campaign.py" active
```

2. If no campaign, invoke planner:
```
Task tool with subagent_type: ftl:planner
Prompt: Plan campaign for: [objective from arguments]
```
Planner returns one of:
- **PROCEED**: Clear plan, continue to step 3
- **CONFIRM**: Show plan, await user approval, then continue to step 3
- **CLARIFY**: Return questions to user, halt

**After CLARIFY**: When user answers, re-invoke planner with clarification context, then continue to step 3.

Planner output includes `### Tasks` section in markdown format.

3. Create campaign (**command is `campaign`, NOT `create`**):
```bash
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

4. Add tasks by piping planner output to stdin:
```bash
echo "$PLANNER_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```
**NOT** `add-task` individually. The parser expects planner's markdown format:
```
### Tasks
1. **slug**: description
   Delta: files
   Depends: none
   Done when: observable
   Verify: command
```

5. Execute each task via Task Mode, then update:
```bash
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```

6. On campaign completion:
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
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
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
