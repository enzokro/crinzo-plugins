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

## Framework Idioms Flow

Framework idioms are **defined in README**, not hardcoded in agents. This makes FTL framework-agnostic.

```
README.md (defines)    →    Router (extracts)    →    Builder (enforces)
     ↓                           ↓                         ↓
## Framework Idioms      Parses section from      Treats as Essential
Required: [...]          README verbatim          constraints
Forbidden: [...]
```

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

### Router (extracts)

- Looks for "## Framework Idioms" section in README
- If found: copies Required/Forbidden lists verbatim to workspace
- If not found but framework mentioned: infers generic guidance
- If no framework: omits Framework Idioms section entirely

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
    Task(ftl:builder) with inline spec — no workspace file
    - 3 tool budget
    - No retry on failure
    - Skip learner (simple change, no pattern extraction)

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
| **router** | Classify tasks, create workspaces, inject memory | Pass framework context to builder |
| **builder** | Transform workspace spec into code | 5 tools max, framework fidelity |
| **planner** | Decompose objectives into verifiable tasks | Verification coherence |
| **learner** | Extract patterns from single workspace (TASK) | Read-only except Key Findings |
| **synthesizer** | Extract meta-patterns from all workspaces (CAMPAIGN) | Detect soft failures |
