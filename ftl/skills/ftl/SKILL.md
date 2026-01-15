---
name: ftl
description: Task execution with learning
version: 2.0.0
---

# FTL Protocol

## Entry Points

| Command | Flow |
|---------|------|
| `/ftl <task>` | Planner → Builder → Observer |
| `/ftl campaign "obj"` | Planner → [Builder]* → Observer |
| `/ftl query "topic"` | `python3 lib/memory.py query "topic"` |
| `/ftl status` | `python3 lib/campaign.py status` |

## Agents

| Agent | Role | Budget |
|-------|------|--------|
| **Planner** | Decompose into verifiable tasks | ∞ |
| **Builder** | Transform spec into code | 3-7 |
| **Observer** | Extract patterns from work | 10 |

## TASK Workflow

```
1. Task(ftl:ftl-planner) with task description
   → Returns plan.json

2. Create workspace:
   python3 lib/workspace.py create --plan plan.json

3. Task(ftl:ftl-builder) with workspace path
   → Returns complete | blocked

4. Task(ftl:ftl-observer) (if blocked OR framework)
   → Updates memory.json
```

## CAMPAIGN Workflow

```
1. Task(ftl:ftl-planner) with objective
   → Returns plan.json

2. python3 lib/campaign.py create "objective"

3. Create all workspaces:
   cat plan.json | python3 lib/campaign.py add-tasks
   python3 lib/workspace.py create --plan plan.json

4. For each task:
   Task(ftl:ftl-builder) with workspace
   python3 lib/campaign.py update-task SEQ complete|blocked

5. Task(ftl:ftl-observer) (analyze all workspaces)

6. python3 lib/campaign.py complete
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
