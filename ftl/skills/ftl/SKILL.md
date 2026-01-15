---
name: ftl
description: Task execution with learning
version: 2.0.0
---

# FTL Protocol

## Entry Points

| Command | Flow |
|---------|------|
| `/ftl <task>` | Explorer (4x) → Planner → Builder → Observer |
| `/ftl campaign "obj"` | Explorer (4x) → Planner → [Builder]* → Observer |
| `/ftl query "topic"` | `python3 lib/memory.py query "topic"` |
| `/ftl status` | `python3 lib/campaign.py status` |

## Agents

| Agent | Role | Model | Budget |
|-------|------|-------|--------|
| **Explorer** | Parallel codebase exploration | haiku | 4 |
| **Planner** | Decompose into verifiable tasks | opus | ∞ |
| **Builder** | Transform spec into code | opus | 3-7 |
| **Observer** | Extract patterns from work | opus | 10 |

## TASK Workflow

```
1. Clear previous exploration:
   python3 lib/exploration.py clear

2. Exploration Phase (4 parallel Haiku agents in single message):
   Task(ftl:ftl-explorer) "mode=structure"
   Task(ftl:ftl-explorer) "mode=pattern, objective={task}"
   Task(ftl:ftl-explorer) "mode=memory, objective={task}"
   Task(ftl:ftl-explorer) "mode=delta, objective={task}"

3. Aggregate outputs (each agent returns raw JSON):
   echo '{output1}
   {output2}
   {output3}
   {output4}' | python3 lib/exploration.py aggregate --objective "{task}" | python3 lib/exploration.py write

4. Task(ftl:ftl-planner) with task + exploration.json
   → Returns plan.json

5. Create workspace:
   python3 lib/workspace.py create --plan plan.json

6. Task(ftl:ftl-builder) with workspace path
   → Returns complete | blocked

7. Task(ftl:ftl-observer) (if blocked OR framework)
   → Updates memory.json
```

## CAMPAIGN Workflow

```
1. Clear previous exploration:
   python3 lib/exploration.py clear

2. Exploration Phase (4 parallel Haiku agents in single message):
   Task(ftl:ftl-explorer) "mode=structure"
   Task(ftl:ftl-explorer) "mode=pattern, objective={objective}"
   Task(ftl:ftl-explorer) "mode=memory, objective={objective}"
   Task(ftl:ftl-explorer) "mode=delta, objective={objective}"

3. Aggregate outputs:
   echo '{output1}
   {output2}
   {output3}
   {output4}' | python3 lib/exploration.py aggregate --objective "{objective}" | python3 lib/exploration.py write

4. Task(ftl:ftl-planner) with objective + exploration.json
   → Returns plan.json

5. python3 lib/campaign.py create "objective"

6. Create all workspaces:
   cat plan.json | python3 lib/campaign.py add-tasks
   python3 lib/workspace.py create --plan plan.json

7. For each task:
   Task(ftl:ftl-builder) with workspace
   python3 lib/campaign.py update-task SEQ complete|blocked

8. Task(ftl:ftl-observer) (analyze all workspaces)

9. python3 lib/campaign.py complete
```

## Workspace Lifecycle

```
.ftl/workspace/NNN_slug_status.xml
```

Status: `active` → `complete` | `blocked`

**Blocking is success** (informed handoff).

## Constraints

| Tier | Meaning | Action |
|------|---------|--------|
| **Essential** | Critical | Escalate |
| **Quality** | Important | Note |

## CLI Reference

```bash
# Exploration
python3 lib/exploration.py clear        # remove exploration.json
python3 lib/exploration.py aggregate --objective "..."  # stdin: JSON lines
python3 lib/exploration.py write        # stdin: exploration dict
python3 lib/exploration.py read         # returns exploration.json
python3 lib/exploration.py get-structure
python3 lib/exploration.py get-pattern
python3 lib/exploration.py get-memory
python3 lib/exploration.py get-delta

# Memory
python3 lib/memory.py context --type BUILD
python3 lib/memory.py add-failure --json '{...}'
python3 lib/memory.py add-pattern --json '{...}'
python3 lib/memory.py query "topic"

# Workspace
python3 lib/workspace.py create --plan plan.json
python3 lib/workspace.py complete path --delivered "..."
python3 lib/workspace.py block path --reason "..."
python3 lib/workspace.py parse path

# Campaign
python3 lib/campaign.py create "objective"
python3 lib/campaign.py add-tasks  # stdin
python3 lib/campaign.py update-task SEQ STATUS
python3 lib/campaign.py next-task   # returns first pending task
python3 lib/campaign.py status
python3 lib/campaign.py active      # returns campaign if active, else null
python3 lib/campaign.py complete
```
