---
name: ftl
description: Task execution with learning
version: 2.3.0
---

# FTL Protocol

## Entry Points

| Command | Flow |
|---------|------|
| `/ftl <task>` | Explorer (4x) → Planner → Builder → Observer |
| `/ftl campaign "obj"` | Explorer (4x) → Planner → [Builder]* → Observer |
| `/ftl query "topic"` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py query "topic"` (semantic ranking) |
| `/ftl status` | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py status` |

## Agents

| Agent | Role | Model | Budget |
|-------|------|-------|--------|
| **Explorer** | Parallel codebase exploration | haiku | 4 |
| **Planner** | Decompose into verifiable tasks | opus | ∞ |
| **Builder** | Transform spec into code | opus | 3-7 |
| **Observer** | Extract patterns from work | opus | 10 |

## Paths

All CLI commands use `${CLAUDE_PLUGIN_ROOT}` for the plugin installation directory:
- `${CLAUDE_PLUGIN_ROOT}/lib/` - Python utilities
- `${CLAUDE_PLUGIN_ROOT}/scripts/` - Shell scripts

## TASK Workflow

```
1. Clear previous exploration:
   python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear

2. Exploration Phase (4 parallel Haiku agents in single message):
   Task(ftl:ftl-explorer) "mode=structure"
   Task(ftl:ftl-explorer) "mode=pattern, objective={task}"
   Task(ftl:ftl-explorer) "mode=memory, objective={task}"
   Task(ftl:ftl-explorer) "mode=delta, objective={task}"

3. Aggregate outputs (explorers write to .ftl/cache/explorer_{mode}.json):
   python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{task}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write

4. Task(ftl:ftl-planner) with task + exploration.json
   → Returns plan.json

5. Create workspace:
   python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan plan.json

6. Task(ftl:ftl-builder) with workspace path
   → Returns complete | blocked

7. Task(ftl:ftl-observer) (always - learns from both success and failure)
   → Updates memory.json
```

## CAMPAIGN Workflow

```
1. Clear previous exploration:
   python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear

2. Exploration Phase (4 parallel Haiku agents in single message):
   Task(ftl:ftl-explorer) "mode=structure"
   Task(ftl:ftl-explorer) "mode=pattern, objective={objective}"
   Task(ftl:ftl-explorer) "mode=memory, objective={objective}"
   Task(ftl:ftl-explorer) "mode=delta, objective={objective}"

3. Aggregate outputs (explorers write to .ftl/cache/explorer_{mode}.json):
   python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "{objective}" | python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write

4. Task(ftl:ftl-planner) with objective + exploration.json
   → Returns plan.json (with DAG dependencies)

5. python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective"

6. Register tasks (no workspace creation yet):
   cat plan.json | python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks

7. Execute tasks with DAG parallelization:
   WHILE python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks returns non-empty:
     ready = ready-tasks output
     FOR EACH task in ready (launch in PARALLEL):
       Create workspace ON-DEMAND (parents now complete, lineage populated):
         echo '{plan.json}' | python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan - --task {SEQ}
       Task(ftl:ftl-builder) with workspace
       python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ complete|blocked

8. Handle cascade (when loop exits, check for stuck tasks):
   cascade = python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status
   IF cascade.state == "stuck":
     python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks
     (Unreachable tasks are marked blocked with blocked_by reference)

9. Task(ftl:ftl-observer) (analyze all workspaces - learn from success and failure)

10. python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete
```

**DAG Parallelization**: Tasks with `depends: ["001", "002"]` wait for both 001 AND 002 to complete.
Tasks with no dependencies or all dependencies complete can run in parallel.

**Cascade Handling**: When a parent task blocks, child tasks become unreachable. The `cascade-status`
command detects this, and `propagate-blocks` marks unreachable tasks as blocked with their blocking
parent reference. This allows campaigns to complete gracefully with partial success.

**On-Demand Workspace Creation**: Workspaces are created AFTER their parent tasks complete.
This enables proper `<lineage>` population with parent deliveries and sibling failure injection.

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

## Semantic Memory

FTL uses semantic embeddings (sentence-transformers) for intelligent memory operations:

| Operation | Semantic Behavior |
|-----------|-------------------|
| **Retrieval** | `--objective` scores memories by cosine similarity, returns most relevant |
| **Deduplication** | 85% semantic similarity threshold prevents near-duplicate entries |
| **Query** | `/ftl query "topic"` ranks results by semantic relevance |

**Hybrid Scoring**: `score = relevance × log₂(cost + 1)` balances semantic relevance with failure cost.

**Fallback**: If sentence-transformers unavailable, falls back to SequenceMatcher string similarity.

## CLI Reference (Exact Syntax)

**IMPORTANT**:
- All paths use `${CLAUDE_PLUGIN_ROOT}` - this variable resolves to the plugin installation directory
- Arguments marked `POS` are positional (no flag). Arguments marked `FLAG` require the flag prefix.

### exploration.py
| Command | Syntax | Notes |
|---------|--------|-------|
| clear | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear` | removes exploration.json |
| aggregate | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate --objective "text"` | stdin: JSON lines |
| aggregate-files | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "text"` | reads .ftl/cache/explorer_*.json |
| write | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write` | stdin: exploration dict |
| read | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py read` | returns exploration.json |
| get-structure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-structure` | |
| get-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-pattern` | |
| get-memory | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-memory` | |
| get-delta | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-delta` | |

### campaign.py
| Command | Syntax | Notes |
|---------|--------|-------|
| create | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective" [--framework NAME]` | `objective` is POS |
| status | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py status` | |
| add-tasks | `cat plan.json \| python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks` | reads stdin, validates DAG (cycle detection) |
| update-task | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ STATUS` | both POS |
| next-task | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py next-task` | returns first pending |
| ready-tasks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks` | returns all tasks ready for parallel execution |
| cascade-status | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status` | detects stuck campaigns due to blocked parents |
| propagate-blocks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks` | marks unreachable tasks as blocked |
| complete | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete [--summary "text"]` | `--summary` is FLAG (not positional!) |
| active | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py active` | returns campaign or null |
| history | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py history` | |
| export | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py export OUTPUT [--start DATE] [--end DATE]` | `OUTPUT` is POS |

### workspace.py
| Command | Syntax | Notes |
|---------|--------|-------|
| create | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan PATH [--task SEQ]` | `--plan` REQUIRED |
| parse | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py parse PATH` | `PATH` is POS |
| complete | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py complete PATH --delivered "text"` | `--delivered` REQUIRED |
| block | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py block PATH --reason "text"` | `--reason` REQUIRED |

### memory.py
| Command | Syntax | Notes |
|---------|--------|-------|
| context | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py context [--type TYPE] [--tags TAGS] [--objective TEXT] [--max-failures N] [--max-patterns N] [--all]` | `--objective` enables semantic retrieval |
| add-failure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-failure --json '{...}'` | `--json` REQUIRED |
| add-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-pattern --json '{...}'` | `--json` REQUIRED |
| query | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py query "term"` | `term` is POS, uses semantic ranking |
