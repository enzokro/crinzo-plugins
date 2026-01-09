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
- Manually update campaign state with CLI commands
- Skip the planner when creating campaigns

The orchestrator (this skill) manages all agent spawning and state transitions.
Violating this constraint causes workspace/campaign desync and gate failures.

**If user asks to use FTL**: Invoke THIS skill. Do not improvise the workflow.

---

## Two Workflows: Task vs Campaign (CRITICAL ARCHITECTURE)

FTL has two fundamentally different workflows. Understanding this prevents agent misuse.

### TASK Mode

```
Request → Router → Builder → Learner → Done
```

- **Scope**: Single decision
- **Pattern agent**: Learner
- **Why**: Surface patterns from one implementation

### CAMPAIGN Mode

```
Objective → Planner → [Router → Builder → update-task]* → Synthesizer → Done
```

- **Scope**: Multiple coordinated decisions
- **Pattern agent**: Synthesizer (at END only)
- **Why**: Meta-patterns from cross-task analysis

### Agent Assignment Matrix

| Agent | Task | Campaign |
|-------|------|----------|
| Router | ✓ | ✓ |
| Builder | ✓ | ✓ |
| Reflector | on fail | on fail |
| Planner | ⊘ | start only |
| **Learner** | **✓** | **⊘ NEVER** |
| **Synthesizer** | ⊘ | **end only** |

### Why This Matters

**Learner and Synthesizer are mutually exclusive by workflow.**

- Learner: Extracts patterns from single task's workspace
- Synthesizer: Extracts meta-patterns from ALL campaign workspaces

### Learner in Campaign = Category Error

Spawning `ftl:learner` during a campaign is not prohibited — it's **incoherent**.

Like asking "what color is the number 7?" The question doesn't make sense.

- Learner operates on: ONE workspace file
- Campaign produces: MANY workspace files
- Pattern extraction needs: ALL files (only synthesizer can see cross-task connections)

If you're in campaign mode and thinking "I should spawn learner now" — that thought signals you've lost track of which workflow you're in.

**Self-check**: Am I in `/ftl <task>` mode? → Learner at end.
Am I in `/ftl campaign` mode? → Synthesizer at end, NO learner.

Cost of violation: ~100k wasted tokens + shallow patterns + missed meta-patterns.

---

## Entry: Route by Intent

| Input Pattern | Mode | Flow |
|---------------|------|------|
| `/ftl <task>` | TASK | router → builder → learner |
| `/ftl campaign <obj>` | CAMPAIGN | planner → tasks[] → synthesize |
| `/ftl query <topic>` | MEMORY | inline CLI query |
| `/ftl status` | STATUS | inline CLI queries |

---

## REQUIRED: Pre-Spawn Context Injection

**You MUST perform these steps before EVERY `ftl:router` spawn. No exceptions.**

### Before spawning router:

1. **Read** `.ftl/cache/session_context.md`
2. **Read** `.ftl/cache/cognition_state.md`
3. **If cache does not exist:** `mkdir -p .ftl/cache`
4. **Prepend contents** to router prompt

### Prompt format:

```
[session_context.md contents]

[cognition_state.md contents]

---

Campaign: ...
Task: ...
```

### Why mandatory:

Skipping injection → router runs redundant `git branch`, `ls .ftl/workspace`, `cat package.json`.
Each redundant call wastes tokens. Injection eliminates ~20 Bash calls per campaign.

### Cache Purpose: Cognition Transfer, Not Just State

The cache is not a convenience — it's **how agents inherit knowledge across phases**.

FTL's cognition loop has distinct phases:
```
LEARNING (planner/router) → EXECUTION (builder) → EXTRACTION (learner/synthesizer)
```

Each phase produces knowledge. The cache transfers that knowledge forward.
Without proper transfer, downstream agents re-learn what upstream agents already knew.

**This is the root cause of exploration creep**: agents read operational state (sequence numbers, file lists) but don't internalize inherited knowledge. They think "let me also check..." because nothing told them checking already happened.

### Cache freshness:

- `session_context.md`: Static (create at campaign start)
- `cognition_state.md`: Dynamic (updated after EVERY agent) — replaces old `workspace_state.md`

**Router also self-checks cache as backup. Both mechanisms must work.**

### REQUIRED: Update Cache After Each Agent

After EVERY agent completes, update `.ftl/cache/cognition_state.md`:

```bash
mkdir -p .ftl/cache

# Compute current state
LAST_SEQ=$(ls .ftl/workspace/ 2>/dev/null | grep -oE '[0-9]+' | sort -n | tail -1 || echo "000")
ACTIVE=$(ls .ftl/workspace/*_active*.md 2>/dev/null | xargs -I{} basename {} 2>/dev/null || echo "none")
RECENT=$(ls -t .ftl/workspace/*_complete*.md 2>/dev/null | head -3 | xargs -I{} basename {} 2>/dev/null || echo "none")

cat > .ftl/cache/cognition_state.md << EOF
# Cognition State
*Updated: $(date)*

## Phase Model

You inherit knowledge from prior phases. You do not re-learn it.

| Phase | Agent | Output |
|-------|-------|--------|
| LEARNING | planner | task breakdown, verification commands |
| SCOPING | router | Delta, Path, precedent |
| EXECUTION | builder | code within Delta |
| EXTRACTION | learner/synthesizer | patterns |

**Category test**: Am I thinking "let me understand X first"?
→ That thought is incoherent. Understanding happened in prior phases.
→ If knowledge feels insufficient, return: "Workspace incomplete: need [X]"

## Inherited Knowledge

Planner analyzed: objective, requirements, verification approach
Router scoped: Delta bounds, data transformation Path, related precedent

**This knowledge is in your workspace file. Read it. Trust it. Execute from it.**

## Operational State

Last sequence: ${LAST_SEQ}
Active: ${ACTIVE}
Recent: ${RECENT}

## If You're About to Explore

STOP. Ask yourself:
1. Is this file in my Delta? If no → out of scope, do not read
2. Did planner/router already analyze this? If yes → knowledge is in workspace
3. Am I learning or executing? If learning → wrong phase

Exploration during execution costs ~10x more than exploration during routing.
The correct response to insufficient knowledge is escalation, not exploration.
EOF
```

**Skipping this update → next agent lacks cognitive grounding → exploration creep → wastes ~100k tokens.**

### Session Context (Create Once)

At campaign start, create `.ftl/cache/session_context.md`:

```bash
cat > .ftl/cache/session_context.md << 'EOF'
# Session Context
*Created: $(date)*

## Git State
Branch: $(git branch --show-current 2>/dev/null || echo "unknown")
Recent commits:
$(git log --oneline -3 2>/dev/null || echo "none")

## Test Commands
$(grep -E '"test"|"typecheck"' package.json 2>/dev/null | head -3 || echo "none detected")

## Codebase Snapshot

Planner has analyzed this codebase. Key findings are embedded in campaign tasks.
Do not re-analyze. Trust the task specifications.
EOF
```

### For builder/learner:

Delta caching handled via SubagentStop → `.ftl/cache/delta_contents.md`.
Agents read this themselves per their instructions.

### Cognitive Grounding Test

An agent reading `cognition_state.md` should immediately know:
1. **What phase they're in** — and therefore what actions are coherent
2. **What knowledge they inherit** — and therefore what they don't need to discover
3. **When to escalate vs explore** — exploration is never the answer mid-execution

If an agent reads the cache and still thinks "let me check...", the cache failed its purpose.

---

## Mode: TASK (Direct Execution)

Main thread spawns phases directly (subagents cannot spawn subagents):

```
1. Task(ftl:router) with task description
   Returns: direct | full | clarify
   If full: also returns workspace path (router creates it)

2a. If direct:
    Task(ftl:builder) — implement immediately, no workspace

2b. If full:
    [Workspace already created by router]
    Task(ftl:builder) — implement within Delta
    If builder fails verification:
      Task(ftl:reflector) — diagnose, return RETRY or ESCALATE

    **TASK mode only**: Task(ftl:learner) — extract patterns, update index
    **CAMPAIGN mode**: See "Two Workflows" section — Synthesizer replaces Learner.

2c. If clarify:
    Return question to user
```

### Direct vs Full Routing (router decides)

**Direct** (no workspace):
- Single file, location obvious
- Mechanical change
- No exploration needed
- No future value

**Full** (with workspace):
- Multi-file or uncertain scope
- Requires exploration
- Understanding benefits future work

Router merges assess + anchor: explores AND routes in one pass.

---

## Mode: CAMPAIGN

For compound objectives requiring multiple coordinated tasks.

### Step 1: Check Active Campaign

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && ACTIVE=$(python3 "$FTL_LIB/campaign.py" active 2>/dev/null)
```

If campaign exists, skip to Step 5 (task execution).

### Step 2: Invoke Planner (REQUIRED)

**DO NOT skip this step. DO NOT manually create campaigns.**

```
Task(ftl:planner) with prompt:
  Objective: $OBJECTIVE_FROM_ARGUMENTS

  Return markdown with ### Tasks section.
```

Planner returns: PROCEED | CONFIRM | CLARIFY

**After CLARIFY**: Re-invoke THIS flow from Step 2. Do NOT continue as Claude Code.

### Step 3: Create Campaign

```bash
python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

**Command is `campaign`, NOT `create`**

### Step 4: Add Tasks from Planner Output

**CRITICAL: Use add-tasks-from-plan, NOT add-task**

```bash
echo "$PLANNER_OUTPUT" | python3 "$FTL_LIB/campaign.py" add-tasks-from-plan
```

Tasks are created with 3-digit sequence numbers (001, 002, etc.).

### Step 5: Execute Each Task

**Campaign loop = Router → Builder → update-task.** (See "Two Workflows" — no Learner)

For each task in sequence, spawn exactly these agents:

**1. Router** — invoke with campaign context:
```
Task(ftl:router) with prompt:
  Campaign: $OBJECTIVE
  Task: $SEQ $SLUG

  [description]
```
The `Campaign:` prefix forces router to create workspace.

**2. Builder** — implement within workspace:

**Pre-spawn injection (REQUIRED):**
1. Read `.ftl/cache/exploration_context.md` (if exists)
2. Read `.ftl/cache/delta_contents.md` (if exists)
3. Prepend to builder prompt

```
Task(ftl:builder) with prompt:
  [exploration_context.md contents if exists]

  [delta_contents.md contents if exists]

  ---
  Workspace: [path returned by router]
```

Exploration context: router's findings (patterns, implementation hints, files examined).
Delta cache: post-edit file contents from prior tasks.

Workspace file remains the specification. Builder reads it for Path, Delta, Verify.
Cache injection prevents re-exploration; ~500k-1M tokens saved per task.

**3. Update cache** — after builder completes:

Use the full cognition_state.md format from "REQUIRED: Update Cache After Each Agent" section above.
This provides cognitive grounding, not just operational state.

**4. Update task** — mark complete:
```bash
python3 "$FTL_LIB/campaign.py" update-task "$SEQ" complete
```

**Synthesizer at campaign end** — see "Two Workflows" section for why Learner is excluded.

update-task enforces workspace gate.

### Step 6: Complete Campaign

```bash
python3 "$FTL_LIB/campaign.py" complete
# Then Task(ftl:synthesizer)
```

**Critical**:
- Create campaign: `campaign.py campaign`, NOT `campaign.py create`
- Add tasks: pipe to `add-tasks-from-plan`, NOT `add-task SEQ SLUG DESC`
- Router prompt MUST include `Campaign:` prefix to force workspace creation

---

## Mode: MEMORY

Query the decision graph for precedent (inlined, no agent spawn):

```bash
source ~/.config/ftl/paths.sh 2>/dev/null && python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
```

Main thread formats and displays ranked decisions.

---

## The FTL Contract

```
┌────────────────────────────────────────────────────────────┐
│ CAMPAIGN              │ TASK                   │ MEMORY    │
├────────────────────────────────────────────────────────────┤
│ Query precedent  ────→│                        │←── query  │
│                       │                        │  (inline) │
│ Delegate task    ────→│ router→builder→        │           │
│                       │ reflector (if fail)    │           │
│                       │ Creates workspace file │           │
│                       │                        │           │
│ Gate on workspace ←───│ Returns _complete.md   │           │
│                       │                        │           │
│ Signal patterns  ────→│                        │←── signal │
│                       │                        │           │
│ Synthesizer (end)────→│ Learner (TASK only)    │←── mine   │
└────────────────────────────────────────────────────────────┘
```

**6 Agents**: router, builder, reflector, learner, planner, synthesizer

---

## Workspace

Task state persists in workspace files:

```
.ftl/workspace/NNN_task-slug_status[_from-NNN].md
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
