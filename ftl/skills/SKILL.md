---
name: ftl
description: Unified development orchestration. Tasks, campaigns, memory.
version: 1.0.0
---

# FTL Protocol

Unified entry point for task execution, campaign orchestration, and memory queries.

## Entry: Route by Intent

| Input Pattern | Mode | Flow |
|---------------|------|------|
| `/ftl <task>` | TASK | assess → (direct\|full) → done |
| `/ftl campaign <obj>` | CAMPAIGN | planner → tasks[] → synthesize |
| `/ftl query <topic>` | MEMORY | surface → context_graph |
| `/ftl status` | STATUS | campaign + workspace + lattice |

---

## Mode: TASK (Direct Execution)

Main thread spawns phases directly (subagents cannot spawn subagents):

```
1. Task(ftl:assess) with task description
   Returns: direct | full | clarify

2a. If direct:
    Task(ftl:code-builder) — implement immediately, no workspace

2b. If full:
    Task(ftl:anchor) — create workspace file
    Gate: verify Path and Delta populated
    Task(ftl:code-builder) — implement within Delta
    Task(ftl:reflect) — extract patterns (conditional)

2c. If clarify:
    Return question to user
```

### Direct vs Full Routing (assess decides)

**Direct** (no workspace):
- Single file, location obvious
- Mechanical change
- No exploration needed
- No future value

**Full** (with workspace):
- Multi-file or uncertain scope
- Requires exploration
- Understanding benefits future work

---

## Mode: CAMPAIGN

For compound objectives requiring multiple coordinated tasks:

```
1. Check active: python3 "$FTL_LIB/campaign.py" active
2. If none: Task(ftl:planner) → create campaign
3. For each task:
   - Query lattice: python3 "$FTL_LIB/context_graph.py" query "$KEYWORDS"
   - Execute via TASK mode
   - Gate on workspace file
   - Signal patterns: python3 "$FTL_LIB/context_graph.py" signal +
4. On complete: Task(ftl:synthesizer)
```

---

## Mode: MEMORY

Query the decision graph for precedent:

```
Task(ftl:surface) with topic
Returns ranked precedents from context_graph
```

---

## The FTL Contract

```
┌────────────────────────────────────────────────────────────┐
│ CAMPAIGN (forge)      │ TASK (tether)          │ MEMORY    │
├────────────────────────────────────────────────────────────┤
│ Query precedent  ────→│                        │←── query  │
│                       │                        │           │
│ Delegate task    ────→│ assess→anchor→build→   │           │
│                       │ reflect                │           │
│                       │ Creates workspace file │           │
│                       │                        │           │
│ Gate on workspace ←───│ Returns _complete.md   │           │
│                       │                        │           │
│ Signal patterns  ────→│                        │←── signal │
│                       │                        │           │
│ Mine (on close)  ────→│                        │←── mine   │
└────────────────────────────────────────────────────────────┘
```

---

## Workspace

Task state persists in workspace files:

```
workspace/NNN_task-slug_status[_from-NNN].md
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
