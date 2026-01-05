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
→ Invoke `ftl:surface` for memory query

### 3. Status Mode
If arguments equal `status`:
```
/ftl status
```
→ Run combined status (campaign + workspace + lattice)

### 4. Task Mode (Default)
Any other input is a direct task:
```
/ftl fix the login bug
/ftl add validation to the form
```
→ Invoke `ftl:assess` for routing, then execute

## Execution Protocol

### Task Mode Flow

1. **Assess** (haiku, fast routing):
```
Task tool with subagent_type: ftl:assess
Prompt: $ARGUMENTS
```
Returns: `direct` | `full` | `clarify`

2a. **If direct** (simple task):
```
Task tool with subagent_type: ftl:code-builder
Prompt: |
  Task: $ARGUMENTS
  [No workspace — direct execution]
```

2b. **If full** (needs workspace):
```
Task tool with subagent_type: ftl:anchor
Prompt: $ARGUMENTS
```
Gate: Read workspace, verify Path and Delta populated.

Then:
```
Task tool with subagent_type: ftl:code-builder
Prompt: |
  Workspace: $WORKSPACE_PATH
```

After completion, check for decision markers and optionally:
```
Task tool with subagent_type: ftl:reflect
Prompt: |
  Workspace: $WORKSPACE_PATH
```

2c. **If clarify**:
Return question to user, halt.

### Campaign Mode Flow

1. Check active campaign:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/campaign.py" active
```

2. If no campaign, invoke planner:
```
Task tool with subagent_type: ftl:planner
Prompt: Plan campaign for: [objective from arguments]
```

3. Create campaign and execute tasks per SKILL.md protocol.

### Query Mode Flow

```
Task tool with subagent_type: ftl:surface
Prompt: [topic from arguments]
```

### Status Mode Flow

```bash
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/campaign.py" status
python3 "$FTL_LIB/workspace.py" stat
```

## Examples

```
/ftl fix typo in README                    → Task mode (direct)
/ftl add user authentication               → Task mode (full)
/ftl campaign implement OAuth with Google  → Campaign mode
/ftl query session handling                → Query mode
/ftl status                                → Status mode
```

## Constraint

Main thread spawns phases directly. Subagents cannot spawn other subagents.
