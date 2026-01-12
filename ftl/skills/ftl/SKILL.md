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

**Router is only for TASK mode.** In Campaign mode, Planner outputs JSON task specs, and `workspace_from_plan.py` generates workspace XML directly - no Router agent needed.

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

### Memory Injection Architecture

Agents fetch their own memory (not pre-injected):
- **Planner**: Fetches ALL memory (unfiltered) for complexity formula
- **Router**: Fetches FILTERED memory (by task tags) for mode decision + workspace

This eliminates redundant memory reads.

### Before TASK mode (Router):

1. Read `.ftl/cache/session_context.md` (git state, tools - NO memory)
2. Read `.ftl/cache/cognition_state.md` (dynamic, updated after each agent)
3. Router fetches filtered memory: `memory.py inject "tags"`

### Before CAMPAIGN mode (Planner):

1. Read `.ftl/cache/session_context.md` (git state, tools - NO memory)
2. Planner fetches all memory: `memory.py inject` (for complexity formula)

### For workspace generation (workspace_from_plan.py):

Memory injection handled automatically:
- Filters by task tags (framework, type, delta files)
- Code context read from Delta files
- No manual injection needed

### After EVERY agent completes:

Hooks automatically update `.ftl/cache/cognition_state.md` via `capture_delta.sh`.

### Cache Files

| File | Type | Purpose |
|------|------|---------|
| `session_context.md` | Static | Git state, project tools (NO memory) |
| `cognition_state.md` | Dynamic | Phase awareness, inherited knowledge |
| `exploration_context.md` | Dynamic | Router findings for builder |
| `delta_contents.md` | Dynamic | File contents from prior tasks |

**Memory is fetched by agents, not cached** - each agent gets exactly what it needs.

---

## Framework Idioms Flow

Framework idioms are **defined in README**, not hardcoded in agents. This makes FTL framework-agnostic.

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

Planner assesses complexity before determining task count:

### Complexity Formula
```
C = (N × 2) + (F / 50000) + (framework × 3)

N = README specification sections
F = Prior Knowledge failure costs (tokens)
framework = none(0), simple(1), moderate(2), high(3)
```

### Task Count by Complexity

| Score | Decomposition |
|-------|---------------|
| C < 8 | 2 tasks: combined SPEC+BUILD → VERIFY |
| 8 ≤ C < 15 | 3 tasks: SPEC → BUILD → VERIFY |
| 15 ≤ C < 25 | 4-5 tasks: SPEC → BUILD_1 → BUILD_2 → VERIFY |
| C ≥ 25 | 5-7 tasks: full decomposition with checkpoints |

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
    Task(ftl:builder, model: sonnet) with inline spec — no workspace file
    - 3 tool budget
    - No retry on failure
    - Skip learner (simple change, no pattern extraction)
    - **Use sonnet** (simple changes don't need Opus reasoning)

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

Router assesses whether task qualifies for DIRECT mode:

| Signal | Mode |
|--------|------|
| Single Delta file, no framework, <100 lines | DIRECT |
| Prior Knowledge shows 0 related failures | DIRECT |
| Multiple files OR framework involved | FULL |
| Prior Knowledge shows related failures | FULL |
| SPEC or VERIFY task type | FULL (always) |

**DIRECT mode**: 3 tools, no workspace, no retry, no learner
**FULL mode**: 5 tools, workspace with Code Context + Framework Idioms, retry once, learner

**Note**: In CAMPAIGN mode, BUILD tasks may still use DIRECT mode if simple. Synthesizer runs at campaign end regardless of individual task modes.

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

### Step 4.5: Generate All Workspaces (NEW - replaces per-task Router)

Extract JSON from Planner output and generate all workspaces at once:

```bash
# Extract JSON block from Planner markdown (between ```json and ```)
PLAN_JSON=$(echo "$PLANNER_OUTPUT" | sed -n '/```json/,/```/p' | sed '1d;$d')

# Generate all workspaces
echo "$PLAN_JSON" | python3 "$FTL_LIB/workspace_from_plan.py" -
```

This replaces spawning Router for each task (saves ~300-400k tokens per campaign).

### Step 5: Execute Each Task

For each task in sequence:

**1. Builder** (workspace already exists from Step 4.5)

Model selection by task type (cost optimization):
| Task Type | Model | Reason |
|-----------|-------|--------|
| VERIFY | sonnet | No code generation, just runs tests |
| DIRECT | sonnet | Simple changes, minimal reasoning |
| SPEC | opus | Complex test design |
| BUILD | opus | Framework idiom enforcement |

```
Task(ftl:builder, model: sonnet if VERIFY else opus) with prompt:
  [exploration_context.md if exists]
  [delta_contents.md if exists]
  ---
  Workspace: .ftl/workspace/NNN_slug_active.xml
```

**2. Update state**
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
| `campaign.py update-task $SEQ complete` | Mark task complete |
| `campaign.py complete` | Complete campaign |
| `workspace_from_plan.py plan.json` | Generate workspaces from Planner JSON |
| `workspace_xml.py complete <path> --delivered "..."` | Atomic: complete workspace |
| `workspace_xml.py block <path> --delivered "..."` | Atomic: block workspace |
| `workspace.py stat` | Workspace status |
| `workspace.py lineage NNN` | Task lineage |
| `memory.py query "$TOPIC"` | Query memory |
| `memory.py inject .ftl/memory.json` | Format memory for injection |

All commands require: `source ~/.config/ftl/paths.sh`

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
| Learner | Confidence threshold met? Evidence cited? |

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

**Note**: In Campaign mode, `workspace_from_plan.py` replaces Router for workspace generation. This saves ~300-400k tokens per campaign by eliminating redundant agent spawns.
