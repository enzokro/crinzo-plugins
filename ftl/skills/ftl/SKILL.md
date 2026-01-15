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
| CAMPAIGN | Objective → Planner → [workspace_from_plan.py → Builder]* → **Synthesizer** | Synthesizer (all workspaces) |

### Agent Matrix

| Agent | Task | Campaign |
|-------|------|----------|
| Router | ✓ | ⊘ (use workspace_from_plan.py) |
| Builder | ✓ | ✓ |
| Planner | ⊘ | start only |
| **Learner** | **✓** | **⊘ NEVER** |
| **Synthesizer** | ⊘ | **end only** |

**Router**: TASK mode only. Campaign uses `workspace_from_plan.py` instead.
**Learner + Synthesizer**: Mutually exclusive by mode.

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

### Before Invoking Agent

| Mode | Read Files | Agent Fetches Memory |
|------|------------|---------------------|
| TASK | `session_context.md`, `cognition_state.md` | Router: `memory.py inject "tags"` |
| CAMPAIGN | `session_context.md` | Planner: `memory.py inject` (all) |

**workspace_from_plan.py**: Handles memory automatically (filters by task tags, reads Delta files).

### After Every Agent
Hooks update `cognition_state.md` via `capture_delta.sh`.

### Cache Files

| File | Type | Purpose |
|------|------|---------|
| `session_context.md` | Static | Git state, project tools |
| `cognition_state.md` | Dynamic | Phase awareness, inherited knowledge |
| `exploration_context.md` | Dynamic | Router findings for builder |
| `delta_contents.md` | Dynamic | File contents from prior tasks |

---

## Framework Idioms Flow

Framework idioms are **defined in README**, not hardcoded in agents. This makes FTL framework-agnostic.

If README mentions a framework but lacks explicit idioms, Planner uses minimal fallback idioms for common frameworks (FastHTML, FastAPI). Projects should define explicit idioms in README for clarity.

| Mode | Flow |
|------|------|
| TASK | README → Router (extracts) → Builder (enforces) |
| CAMPAIGN | README → Planner (extracts to JSON) → workspace_from_plan.py → Builder (enforces) |

### README Structure (project defines)

```markdown
## Framework Idioms
Required:
- [pattern 1 - e.g., "Use @rt decorator for routes"]
- [pattern 2 - e.g., "Return component trees, not strings"]

Forbidden:
- [anti-pattern 1 - e.g., "Raw HTML strings with f-strings"]
- [anti-pattern 2 - e.g., "Manual string concatenation"]
```

### Extraction (mode-dependent)

**TASK mode (Router)**:
- Looks for "## Framework Idioms" section in README
- If found: copies Required/Forbidden lists verbatim to workspace
- If not found but framework mentioned: infers generic guidance
- If no framework: omits Framework Idioms section entirely

**CAMPAIGN mode (Planner → workspace_from_plan.py)**:
- Planner extracts idioms to JSON output
- workspace_from_plan.py copies idioms to each workspace
- No Router agent needed

### Builder (enforces)

- Framework Idioms in workspace are **Essential** constraints
- Required items MUST be used
- Forbidden items MUST NOT appear
- Quality checkpoint verifies idiom compliance

### Planner (signals)

```markdown
### Downstream Impact
- Framework: [name] (Builder must use idioms)
- Framework complexity: [low | moderate | high]
```

---

## Adaptive Decomposition

Planner calculates task complexity using:
- N = README specification sections
- F = Prior Knowledge failure costs (tokens)
- Framework complexity factor (none/simple/moderate/high)

See `planner.md` for complete formula. Task counts scale from 2 (simple) to 7 (complex).

**If README mandates specific task count**, planner notes deviation but follows README.

---

## Enhanced Workspace Structure

Router creates workspaces with embedded context:

### Code Context (if Delta file exists)
```markdown
## Code Context
### {delta_file}
```python
{current file contents, first 60 lines}
```
Exports: {function_name(), ClassName}
Imports: {from X import Y}

### Task Lineage
Parent: {prior task slug} | none
Prior delivery: {what parent completed}
```

### Framework Idioms (if framework specified)
```markdown
## Framework Idioms
Framework: FastHTML
Required:
- Use @rt decorator for routes
- Return component trees (Div, Ul, Li), NOT f-strings
- Use Form/Input/Button for forms
Forbidden:
- Raw HTML string construction with f-strings
- Manual string concatenation for templates
```

**Framework Idioms are Essential constraints** - Builder MUST use Required items and MUST NOT use Forbidden items.

---

## Mode: TASK

```
1. Task(ftl:router) with task description
   Returns: direct | full | clarify

2a. If direct:
    Task(ftl:ftl-builder) with inline spec
    - 3 tool budget
    - No retry on failure
    - Skip learner (simple change, no pattern extraction)
    - Uses Sonnet model (simple changes don't need Opus reasoning)

2b. If full:
    Task(ftl:builder) — workspace created by router
    - 5 tool budget
    - Retry once on Known Failure match
    - Code Context + Framework Idioms in workspace
    Task(ftl:learner) — extract patterns

2c. If clarify:
    Return question to user
```

### DIRECT Mode Routing

Router determines DIRECT vs FULL mode based on:
- File count and complexity
- Framework involvement
- Related failure history
- Task type (SPEC/BUILD/VERIFY)

See `router.md` for complete signal table.

**DIRECT mode**: 3 tools, no workspace, no retry, no learner
**FULL mode**: 5 tools, workspace with Code Context + Framework Idioms, retry once, learner

**Campaign DIRECT mode (VERIFY tasks)**:
Final VERIFY task may run inline without spawning an agent:
- No workspace file created
- On **pass**: Campaign completes
- On **fail**: Campaign blocked, error logged

**Note**: BUILD tasks may use DIRECT mode if simple. Synthesizer runs at campaign end regardless.

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
  [session_context.md contents - git state, tools]

  Objective: [objective from user]
```

Planner fetches its own memory (Step 0 in planner.md).

Returns: PROCEED | CONFIRM | CLARIFY

### Step 3: Create Campaign

```bash
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

### Step 4: Add Tasks

```bash
echo "$PLANNER_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```

### Step 4.5: Generate All Workspaces

```bash
PLAN_JSON=$(echo "$PLANNER_OUTPUT" | sed -n '/```json/,/```/p' | sed '1d;$d')
echo "$PLAN_JSON" | python3 "$FTL_LIB/workspace_from_plan.py" -
python3 "$FTL_LIB/campaign.py" sync-from-plan
```

### Step 5: Execute Each Task

For each task in sequence:

**1. Builder** (workspace from Step 4.5, except DIRECT mode)

Agent selection by task type (cost optimization):
| Task Type | Agent | Model | Reason |
|-----------|-------|-------|--------|
| VERIFY (with workspace) | ftl:ftl-builder-verify | sonnet | No code generation, just runs tests |
| VERIFY (final, DIRECT) | inline | - | No agent spawn, runs verify command directly |
| DIRECT | ftl:ftl-builder-verify | sonnet | Simple changes, minimal reasoning |
| SPEC | ftl:ftl-builder | opus | Complex test design |
| BUILD | ftl:ftl-builder | opus | Framework idiom enforcement |

For VERIFY tasks with workspace:
```
Task(ftl:ftl-builder-verify) with prompt:
  Workspace: .ftl/workspace/NNN_slug_active.xml
```

For VERIFY tasks in DIRECT mode (final campaign task, no workspace):
```bash
# Run verify command inline - no agent spawn needed
uv run pytest test_app.py -v
# Skip status update (no workspace file to mark complete)
# Campaign completion handles overall status
```

For DIRECT mode (BUILD):
```
Task(ftl:ftl-builder-verify) with inline spec (no workspace path)
```

For SPEC/BUILD tasks:
```
Task(ftl:ftl-builder) with prompt:
  [exploration_context.md if exists]
  [delta_contents.md if exists]
  ---
  Workspace: .ftl/workspace/NNN_slug_active.xml
```

**2. Update state** (skip for DIRECT mode)

| Workspace State | Action |
|-----------------|--------|
| `${SEQ}_*_complete*.xml` exists | `campaign.py update-task $SEQ complete` |
| `${SEQ}_*_active*.xml` + Delta files exist | Complete workspace on behalf of builder |
| Active workspace + Delta missing | Warning, cannot complete |

```bash
source ~/.config/ftl/paths.sh 2>/dev/null
COMPLETE_WS=$(ls .ftl/workspace/${SEQ}_*_complete*.xml 2>/dev/null | head -1)
ACTIVE_WS=$(ls .ftl/workspace/${SEQ}_*_active*.xml 2>/dev/null | head -1)
if [ -n "$COMPLETE_WS" ]; then
  python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
elif [ -n "$ACTIVE_WS" ]; then
  DELTA=$(python3 "$FTL_LIB/workspace_xml.py" parse "$ACTIVE_WS" 2>/dev/null | jq -r '.delta[]')
  ALL_EXIST=true; for f in $DELTA; do [ ! -f "$f" ] && ALL_EXIST=false; done
  [ "$ALL_EXIST" = true ] && python3 "$FTL_LIB/workspace_xml.py" complete "$ACTIVE_WS" --delivered "Orchestrator"
  python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
fi
```

Hooks update `cognition_state.md` automatically.

### Step 6: Complete Campaign (Conditional Synthesizer)

```bash
python3 "$FTL_LIB/campaign.py" complete
```

**Synthesizer Gate**:

| Condition | Action |
|-----------|--------|
| Blocked workspaces > 0 | RUN synthesizer |
| New framework (not in memory) | RUN synthesizer |
| All complete + framework known | SKIP; run `memory.py add-source $CAMPAIGN_ID` |

```bash
BLOCKED=$(find .ftl/workspace -name "*_blocked.xml" 2>/dev/null | wc -l)
FW=$(python3 "$FTL_LIB/campaign.py" get-framework 2>/dev/null)
NEW_FW=$(python3 "$FTL_LIB/memory.py" check-new-frameworks "$FW" 2>/dev/null)
if [ "$BLOCKED" -gt 0 ] || [ -n "$NEW_FW" ]; then
  Task(ftl:synthesizer)
else
  python3 "$FTL_LIB/memory.py" add-source "$CAMPAIGN_ID"
fi
```

Synthesizer reads ONLY workspace files (not source code).

---

## Mode: MEMORY

```bash
source ~/.config/ftl/paths.sh 2>/dev/null
python3 "$FTL_LIB/memory.py" query "$TOPIC"
```

---

## Workspace

```
.ftl/workspace/NNN_task-slug_status.xml
```

Status: `active` | `complete` | `blocked`

---

## CLI Reference

| Command | Purpose |
|---------|---------|
| `campaign.py active` | Check active campaign |
| `campaign.py campaign "$OBJ"` | Create campaign |
| `campaign.py add-tasks-from-plan` | Add tasks from planner output |
| `campaign.py sync-from-plan` | Copy tasks from plan.json to campaign for audit trail |
| `campaign.py update-task $SEQ complete` | Mark task complete |
| `campaign.py complete` | Complete campaign |
| `campaign.py get-framework` | Get framework from workspace files |
| `workspace_from_plan.py plan.json` | Generate workspaces from Planner JSON |
| `workspace_xml.py complete <path> --delivered "..."` | Atomic: complete workspace |
| `workspace_xml.py block <path> --delivered "..."` | Atomic: block workspace |
| `workspace.py stat` | Workspace status |
| `workspace.py lineage NNN` | Task lineage |
| `memory.py query "$TOPIC"` | Query memory |
| `memory.py inject .ftl/memory.json` | Format memory for injection |
| `memory.py check-new-frameworks <fw>` | Check if framework is new to memory |
| `memory.py add-source <campaign>` | Add campaign to pattern sources |

All commands require: `source ~/.config/ftl/paths.sh`

---

## Hooks Reference

### capture_delta.sh (SubagentStop)
**Trigger:** After every agent completes (router, builder, builder-verify, learner, planner, synthesizer)

**Purpose:** Update cognition cache to enable knowledge inheritance between agents.

**Creates/Updates:**
| File | Content |
|------|---------|
| `.ftl/cache/cognition_state.md` | Phase model, active/recent workspaces, recent learnings |
| `.ftl/cache/delta_contents.md` | Current Delta file contents for builder/learner |

### capture_exploration.sh (SubagentStop: Router only)
**Trigger:** After Router agent completes

**Purpose:** Extract structured context from Router's workspace XML for Builder injection.

**Creates:**
| File | Content |
|------|---------|
| `.ftl/cache/exploration_context.md` | Implementation spec, code context, framework idioms, prior knowledge |

---

## Design Principles

| Principle | Meaning |
|-----------|---------|
| Present over future | Current request only |
| Concrete over abstract | Specific solution, not framework |
| Explicit over clever | Clarity over sophistication |
| Edit over create | Modify existing first |
| Framework fidelity | Use idioms, not raw equivalents |
| Quality beyond tests | Tests pass ≠ architecturally correct |

No new abstractions. No files outside Delta.

---

## Constraint Tiering

All agents use tiered constraints:

| Tier | Meaning | Action |
|------|---------|--------|
| **Essential** | Critical invariant | Escalate if violated |
| **Quality** | Important but recoverable | Note in output |

This replaces MUST/NEVER/CRITICAL with clear priority levels.

**Example (Builder):**
- Essential: Tool budget (5 max), Framework Idioms, block signals
- Quality: Delivered section filled, Code Context exports preserved

---

## Quality Checkpoints

Every agent runs a quality checkpoint before completing:

| Agent | Checks |
|-------|--------|
| Builder | Framework idioms used? Delivered section filled? |
| Router | Delta specific? Verify executable? Framework context? |
| Planner | All tasks verifiable? Dependencies ordered? |
| Synthesizer | Soft failures detected? Generalizable patterns? |
| Learner | Pattern extraction rules met? Evidence cited? |

Quality checkpoint catches issues before they propagate.

---

## 5 Agents

| Agent | Role | Key Constraint |
|-------|------|----------------|
| **router** | Classify tasks (TASK mode only) | Pass framework context to builder |
| **builder** | Transform workspace spec into code | 5 tools max, framework fidelity |
| **planner** | Decompose objectives + output JSON specs | Verification coherence |
| **learner** | Extract patterns from single workspace (TASK) | Read-only except Key Findings |
| **synthesizer** | Extract meta-patterns from all workspaces (CAMPAIGN) | Verify blocks before extraction |

**Note**: In Campaign mode, `workspace_from_plan.py` replaces Router for workspace generation.
