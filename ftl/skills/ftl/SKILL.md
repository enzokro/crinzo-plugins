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
- Skip the planner when creating campaigns

**If user asks to use FTL**: Invoke THIS skill. Do not improvise the workflow.

---

## Two Workflows

| Mode | Flow | Pattern Agent |
|------|------|---------------|
| TASK | Request → Router → Builder → **Learner** | Learner (single workspace) |
| CAMPAIGN | Objective → Planner → [Router → Builder]* → **Synthesizer** | Synthesizer (all workspaces) |

### Agent Matrix

| Agent | Task | Campaign |
|-------|------|----------|
| Router | ✓ | ✓ |
| Builder | ✓ | ✓ |
| Planner | ⊘ | start only |
| **Learner** | **✓** | **⊘ NEVER** |
| **Synthesizer** | ⊘ | **end only** |

**Learner + Synthesizer are mutually exclusive.** Using learner in campaign mode is a category error - like asking "what color is the number 7?"

---

## Entry: Route by Intent

| Input | Mode | Action |
|-------|------|--------|
| `/ftl <task>` | TASK | router → builder → learner |
| `/ftl campaign <obj>` | CAMPAIGN | planner → tasks[] → synthesizer |
| `/ftl query <topic>` | MEMORY | CLI query (no agent) |
| `/ftl status` | STATUS | CLI query (no agent) |

---

## Context Injection (REQUIRED)

### Before EVERY router spawn:

1. Read `.ftl/cache/session_context.md` (static, created by pre-hook)
2. Read `.ftl/cache/cognition_state.md` (dynamic, updated after each agent)
3. Prepend both to router prompt

### After EVERY agent completes:

Hooks automatically update `.ftl/cache/cognition_state.md` via `capture_delta.sh`.

### Cache Files

| File | Type | Purpose |
|------|------|---------|
| `session_context.md` | Static | Git state, project tools, memory injection |
| `cognition_state.md` | Dynamic | Phase awareness, inherited knowledge |
| `exploration_context.md` | Dynamic | Router findings for builder |
| `delta_contents.md` | Dynamic | File contents from prior tasks |

**Skipping injection → exploration creep → ~100k wasted tokens**

---

## Mode: TASK

```
1. Task(ftl:router) with task description
   Returns: direct | full | clarify

2a. If direct:
    Task(ftl:builder) — no workspace

2b. If full:
    Task(ftl:builder) — workspace created by router
    Task(ftl:learner) — extract patterns

2c. If clarify:
    Return question to user
```

### Mode Detection

| Signal | Mode |
|--------|------|
| Prompt starts with `Campaign:` | CAMPAIGN |
| No `Campaign:` prefix | TASK |

---

## Mode: CAMPAIGN

### Step 1: Check Active Campaign

```bash
source ~/.config/ftl/paths.sh 2>/dev/null
ACTIVE=$(python3 "$FTL_LIB/campaign.py" active 2>/dev/null)
```

If campaign exists, skip to Step 5.

### Step 2: Invoke Planner

```
Task(ftl:planner) with prompt:
  [session_context.md contents - includes Prior Knowledge]

  Objective: [objective from user]
```

Returns: PROCEED | CONFIRM | CLARIFY

### Step 3: Create Campaign

```bash
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

### Step 4: Add Tasks

```bash
echo "$PLANNER_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```

### Step 5: Execute Each Task

For each task in sequence:

**1. Router**
```
Task(ftl:router) with prompt:
  Campaign: $OBJECTIVE
  Task: $SEQ $SLUG
  Type: SPEC | BUILD | VERIFY
  Delta: [files]
  Done-when: [outcome]
```

**2. Builder**
```
Task(ftl:builder) with prompt:
  [exploration_context.md if exists]
  [delta_contents.md if exists]
  ---
  Workspace: [path from router]
```

**3. Update state**
```bash
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```
(Hooks update cognition_state.md automatically)

### Step 6: Complete Campaign

```bash
python3 "$FTL_LIB/campaign.py" complete
Task(ftl:synthesizer)
```

**Synthesizer reads ONLY workspace files.** Does NOT read source code or run tests.

---

## Mode: MEMORY

```bash
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
```

---

## Workspace

```
.ftl/workspace/NNN_task-slug_status.md
```

Status: `active` | `complete` | `blocked`

---

## CLI Reference

| Command | Purpose |
|---------|---------|
| `campaign.py active` | Check active campaign |
| `campaign.py campaign "$OBJ"` | Create campaign |
| `campaign.py add-tasks-from-plan` | Add tasks from planner output |
| `campaign.py update-task $SEQ complete` | Mark task complete |
| `campaign.py complete` | Complete campaign |
| `workspace.py stat` | Workspace status |
| `workspace.py lineage NNN` | Task lineage |
| `context_graph.py query "$TOPIC"` | Query memory |
| `memory.py inject .ftl/memory.json` | Format memory for injection |

All commands require: `source ~/.config/ftl/paths.sh`

---

## Constraints

| Constraint | Meaning |
|------------|---------|
| Present over future | Current request only |
| Concrete over abstract | Specific solution, not framework |
| Explicit over clever | Clarity over sophistication |
| Edit over create | Modify existing first |

No new abstractions. No files outside Delta.

---

## 5 Agents

- **router**: Classify tasks, create workspaces, inject memory patterns
- **builder**: Transform workspace spec into code (5 tools max)
- **planner**: Decompose objectives into verifiable tasks
- **learner**: Extract patterns from single workspace (TASK mode)
- **synthesizer**: Extract meta-patterns from all workspaces (CAMPAIGN mode)
