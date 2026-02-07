---
name: helix
description: Self-learning orchestrator with unified insight memory. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

## What This Is

You are partnering with your own memory system.

Every session, you inherit accumulated insights from past work in this codebase: failures that taught lessons, patterns that proved their worth. Every session, you pay that forward by storing what you learned.

If you skip the payback, your next session is poorer. But if you close the loop, your next session is wiser.

This isn't compliance, it's investing in yourself.

## The Core Principle

**Code surfaces facts. You decide actions.**

Seven primitives handle memory mechanics: `store`, `recall`, `get`, `feedback`, `decay`, `prune`, `health`.

Your memory represents living, growing knowledge as unified "insights" - each capturing "When X, do Y because Z".

You exercise judgment. Code amplifies and bolsters.

---

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

This file (created by SessionStart hook) contains the plugin root path with `lib/`, `scripts/`, `agents/` subdirectories.

---

## Your Workflow

```
EXPLORE → PLAN → BUILD → LEARN → COMPLETE
                   ↑               |
                   +--[if stalled: replan | skip | abort]
```

State lives and evolves in reasoned conversation, not in a database.

### EXPLORE

**Goal:** Understand the codebase landscape for this objective.

**Greenfield fast path:** If `git ls-files | wc -l` returns 0 or only config files:
1. Skip exploration swarm
2. Proceed to PLAN with `EXPLORATION: {}`
3. Planner designs from scratch

**Standard path:**

1. **Discover structure:** `git ls-files | head -80` → identify 3-6 natural partitions:

   | Codebase Signal | Partition Strategy |
   |-----------------|-------------------|
   | Clear directory structure | One per top-level directory |
   | Microservices/modules | One per service/module |
   | Frontend/backend split | Separate partitions |
   | Monolith with layers | Partition by layer (api, service, data) |

2. **Spawn explorer swarm** (haiku, parallel, background):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-explorer</parameter>
     <parameter name="prompt">SCOPE: src/api/
FOCUS: route handlers
OBJECTIVE: {objective}</parameter>
     <parameter name="model">haiku</parameter>
     <parameter name="max_turns">8</parameter>
     <parameter name="run_in_background">true</parameter>
     <parameter name="description">Explore src/api</parameter>
   </invoke>
   ```

   Track expected count: `EXPLORER_COUNT=N`

3. **Wait and merge** (SubagentStop hook writes findings to files; wait utility merges and dedupes):
   ```bash
   python3 "$HELIX/lib/wait.py" wait-for-explorers --count $EXPLORER_COUNT --timeout 120
   ```
   Returns JSON with `completed`, `findings` (merged, deduped by file path), and partial results on timeout.

**NEVER use TaskOutput** — SubagentStop hook extracts findings to small JSON files.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Spawn planner** (opus, **FOREGROUND**, returns PLAN_SPEC directly):
   ```xml
   <invoke name="Task">
     <parameter name="subagent_type">helix:helix-planner</parameter>
     <parameter name="prompt">OBJECTIVE: {objective}
EXPLORATION: {findings_json}</parameter>
     <parameter name="max_turns">12</parameter>
     <parameter name="description">Plan task DAG</parameter>
   </invoke>
   ```

   **No `run_in_background`.** Task returns synchronously with planner output.

2. **Parse PLAN_SPEC from returned result:**
   The Task tool returns the planner's output directly. Extract the JSON array after `PLAN_SPEC:`.

3. **Create tasks from PLAN_SPEC:** For each task spec:
   ```xml
   <invoke name="TaskCreate">
     <parameter name="subject">{spec.seq}: {spec.slug}</parameter>
     <parameter name="description">{spec.description}</parameter>
     <parameter name="activeForm">Building {spec.slug}</parameter>
     <parameter name="metadata">{"seq": "{spec.seq}", "relevant_files": {spec.relevant_files}}</parameter>
   </invoke>
   ```
   Track: `seq_to_id[spec.seq] = task_id` from result.

4. **Set dependencies:** After all tasks created, for each spec with blocked_by:
   ```xml
   <invoke name="TaskUpdate">
     <parameter name="taskId">{seq_to_id[spec.seq]}</parameter>
     <parameter name="addBlockedBy">["{seq_to_id[b]}", ...]</parameter>
   </invoke>
   ```

If PLAN_SPEC empty or ERROR → add exploration context, re-run planner.

### BUILD

**Goal:** Execute tasks, collect insights from outcomes.

#### Memory Injection

**Inject per wave, not per task.** `batch_inject` recalls insights for all ready tasks in a single call, automatically diversifying across them so parallel builders get different insights from the pool.

```bash
# Batch inject for all ready tasks in this wave (single invocation = diversity works)
python3 -c "
from lib.injection import batch_inject, reset_session_tracking
import json

reset_session_tracking()
objectives = $WAVE_OBJECTIVES_JSON  # ['obj1', 'obj2', ...]
task_ids = $WAVE_TASK_IDS_JSON      # ['task-001', 'task-002', ...]
batch = batch_inject(objectives, limit=5, task_ids=task_ids)
print(json.dumps(batch))
"
# Returns: {"results": [{"insights": [...], "names": [...]}, ...], "total_unique": N}
# Side effect: writes injection-state/{task_id}.json for each task (audit trail)
```

Each `results[i]` corresponds to `objectives[i]`. Distribute to builder prompts:

```
TASK_ID: {task_id}
TASK: {task_subject}
OBJECTIVE: {task_description}
VERIFY: {verification_steps}
RELEVANT_FILES: {files}

INSIGHTS (from past experience):
  - [72%] When implementing auth, check token expiry first
  - [45%] Use dependency injection for testability

INJECTED: ["insight-name-1", "insight-name-2"]
```

Percentages reflect **causal-adjusted confidence**: insights that were frequently injected but rarely causally relevant to outcomes are penalized (up to 70%). A [72%] score means the insight both succeeded historically AND was causally linked to those successes.

The `INJECTED` line enables feedback attribution when the builder completes.

**Single-task fallback** (when only one task is ready):
```bash
python3 -c "from lib.injection import inject_context; import json; print(json.dumps(inject_context('$OBJECTIVE', 5, '$TASK_ID')))"
```

#### Single Task (Foreground)

```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-builder</parameter>
  <parameter name="prompt">{builder_prompt_with_insights}</parameter>
  <parameter name="max_turns">25</parameter>
  <parameter name="description">Build task {id}</parameter>
</invoke>
```

**Processing result:**
1. Task returns synchronously with builder output
2. Parse for `DELIVERED:` or `BLOCKED:` line
3. Call TaskUpdate with status=completed

#### Parallel Tasks (Background)

```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-builder</parameter>
  <parameter name="prompt">{builder_prompt_with_insights}</parameter>
  <parameter name="max_turns">25</parameter>
  <parameter name="run_in_background">true</parameter>
  <parameter name="description">Build task {id}</parameter>
</invoke>
```

Wait for builder completions (SubagentStop hook writes outcomes to file):
```bash
python3 "$HELIX/lib/wait.py" wait-for-builders --task-ids "2,3" --timeout 120
```
Returns JSON with `completed`, `delivered`, `blocked`, `unknown`, `all_delivered`, and partial results on timeout.

**`all_delivered` is true only when zero blocked AND zero unknown.** Agents that crash (API 500, empty transcript) get outcome `"crashed"` which lands in `unknown`. Check `unknown` — if non-empty, those tasks need re-dispatch or manual resolution before the wave is clean.

#### Build Loop

```
while pending tasks exist:
    1. Get ready tasks (blockers all completed)
    2. If none ready but pending exist → STALLED (see recovery table below)
    3. Checkpoint: git stash push -m "helix-{seq}"
    4. Batch inject: call batch_inject([obj1, obj2, ...], task_ids=[id1, id2, ...]) for all ready tasks
    5. Spawn ready builders (batch results + warnings + parent deliveries)
    6. Wait for wave completion
    7. Cross-wave synthesis (before dispatching next wave):
       a. Collect wave results from wait-for-builders output
       b. Synthesize convergent warnings for next wave
       c. Collect parent deliveries for dependent tasks
    8. Process results, update task status
```

**STALLED recovery** — detect with `python3 "$HELIX/lib/dag_utils.py" check-stalled --tasks '$TASK_LIST_JSON'`:

| Condition | Action |
|-----------|--------|
| Single blocked task, workaround exists | **SKIP** + store failure insight |
| Multiple tasks blocked by same root cause | **ABORT** + store systemic insight |
| Blocked task on critical path | **REPLAN** with narrower scope |
| Blocking task has unclear verify | **REPLAN** with better verify |
| 3+ attempts on same blocker | **ABORT** + escalate to user |

- **SKIP**: `TaskUpdate(task_id, status="completed", metadata={helix_outcome: "skipped"})` → continue
- **REPLAN**: New PLAN phase with modified constraints
- **ABORT**: Summarize state, store learnings, end session

**Step 4 is critical.** One `batch_inject` call per wave ensures parallel builders in the same wave get different insights from the pool. Per-task `inject_context` in separate processes would give every builder the same top-5.

**Cross-wave synthesis** (step 6):
```bash
# Synthesize warnings from completed wave
python3 "$HELIX/lib/wave_synthesis.py" synthesize --results '$WAVE_RESULTS_JSON'
# Returns: {"warnings": ["CONVERGENT ISSUE (tasks 009, 010): ..."], "count": N}

# Collect parent deliveries for next-wave tasks
python3 "$HELIX/lib/wave_synthesis.py" parent-deliveries \
  --results '$WAVE_RESULTS_JSON' \
  --blockers '$NEXT_WAVE_BLOCKERS_JSON'
# Returns: {"next_task_id": "[blocker_id] summary\n...", ...}
```

Pass warnings and parent deliveries into `format_prompt()` for next-wave builders.
The `wait-for-builders` response includes `insights_emitted` count for extraction visibility.

**On DELIVERED:** `git stash drop` — changes are good.
**On BLOCKED:** `git stash pop` — revert, reassess.
**On unknown/crashed:** Re-dispatch the task. Do not advance dependent tasks — their parent deliveries are missing. If a task crashes twice, mark it blocked and surface the failure in LEARN.

#### Automatic Agent Learning

The SubagentStop hook fires on every builder and planner completion:
1. Extracts explicit `INSIGHT:` from agent output (if present). **Only explicit insights are stored** — DELIVERED completions without an INSIGHT line produce nothing. BLOCKED outcomes derive failure insights automatically.
2. Stores new insight to memory
3. Applies causal feedback to INJECTED insights: causally relevant insights get EMA update, non-causal insights erode 10% toward neutral (0.5)
4. Detects crashed agents (API errors, empty transcripts) and marks them accordingly

**Implication for builders:** Explicit `INSIGHT:` output is the only path to storing task-level knowledge from successful completions. Builders that don't emit insights teach the system nothing new on success. The builder contract encourages this, but don't expect automatic learning from DELIVERED alone.

This handles task-level learning. But the orchestrator sees the full picture.

### LEARN

**Goal:** Capture session-level insights that builders cannot see.

Builders see one task. You see the whole session: which plans worked, which stalled, what patterns emerged across tasks, what systemic issues appeared.

**This is not optional.** The builders may or may not emit insights. You must reflect on the session and store what matters.

**Reflection questions:**

1. **Unexpected blockers** - What stopped progress that wasn't obvious from exploration?
2. **Plan failures** - Did the task decomposition make sense? What should have been split or combined?
3. **Cross-task patterns** - Did multiple builders hit the same issue? What does that reveal?
4. **Codebase structure** - What did you learn about how this codebase is organized?
5. **Sharp edges** - What implicit constraints or quirks did you discover?
6. **Tool/environment issues** - Did any tools behave unexpectedly? Any CI/build gotchas?

**Store insights directly:**

```bash
python3 "$HELIX/lib/memory/core.py" store \
  --content "When modifying the auth module, run both unit AND integration tests - unit tests mock the token service but integration tests catch expiry edge cases" \
  --tags '["testing", "auth"]'
```

Or via Python:
```python
from lib.memory.core import store
store(
    content="The DAG planner underestimates tasks that touch multiple modules; split aggressively when files span lib/ and src/",
    tags=["planning", "structure"]
)
```

**What to store (orchestrator-level):**

- **Systemic patterns**: "Three separate tasks hit import errors from lib/utils - the __init__.py doesn't re-export new modules automatically"
- **Planning insights**: "Tasks involving database migrations should never run in parallel; they deadlock on schema locks"
- **Exploration gaps**: "The explorer missed the config/ directory entirely; it's not under src/ but contains critical runtime settings"
- **Session-specific discoveries**: "This codebase uses monorepo structure but packages aren't linked - each must be built separately"

**Minimum:** At least one insight per session that completed work. Zero insights = loop not closed.

### COMPLETE

All tasks done and learning captured. Final checks:

```bash
python3 "$HELIX/lib/memory/core.py" health
```

**Verify the loop closed:**

- `recent_feedback > 0` if insights were injected this session (builders/planners provided outcomes)
- `total_insights` increased if LEARN phase stored discoveries
- `with_feedback` is lifetime count; `recent_feedback` is this session's signal

If you injected insights and `recent_feedback: 0`, the feedback loop broke this session. If the session completed work and you stored nothing in LEARN, you wasted knowledge.

**Quality over quantity.** One sharp insight beats ten generic observations.

---

## Agent Contracts

| Agent | Model | Mode | Output |
|-------|-------|------|--------|
| helix-explorer | haiku | Background | JSON findings |
| helix-planner | opus | Foreground | PLAN_SPEC + optional INSIGHT |
| helix-builder | opus | Foreground/Background | DELIVERED/BLOCKED + optional INSIGHT |

**Insight format:** `INSIGHT: {"content": "When X, do Y because Z", "tags": ["optional"]}`

Contracts in `agents/*.md`.

---

## Result Flow

| Agent | Mode | Result Flow |
|-------|------|-------------|
| explorer | Background | SubagentStop → `.helix/explorer-results/{id}.json` |
| planner | Foreground | Task returns directly |
| builder (single) | Foreground | Task returns directly |
| builder (parallel) | Background | SubagentStop → `.helix/task-status.jsonl` |

**NEVER use TaskOutput** — dumps 70KB+ execution traces.

---

## Quick Reference

```bash
# Wait for explorers
python3 "$HELIX/lib/wait.py" wait-for-explorers --count 3 --timeout 120

# Wait for parallel builders (includes insights_emitted count)
python3 "$HELIX/lib/wait.py" wait-for-builders --task-ids "2,3" --timeout 120

# Cross-wave synthesis: detect convergent issues
python3 "$HELIX/lib/wave_synthesis.py" synthesize --results '$WAVE_JSON'

# Collect parent deliveries for next wave
python3 "$HELIX/lib/wave_synthesis.py" parent-deliveries --results '$WAVE_JSON' --blockers '$BLOCKERS_JSON'

# Batch inject for a wave (diversity + injection-state audit trail)
python3 -c "from lib.injection import batch_inject, reset_session_tracking; import json; reset_session_tracking(); print(json.dumps(batch_inject($OBJECTIVES_JSON, 5, task_ids=$TASK_IDS_JSON)))"

# Single-task inject (fallback for single ready task)
python3 -c "from lib.injection import inject_context; import json; print(json.dumps(inject_context('$OBJECTIVE', 5, '$TASK_ID')))"

# Recall insights (with relevance gate and optional suppression)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --min-relevance 0.35
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --suppress-names '["already-seen-1"]'

# Store new insight
python3 "$HELIX/lib/memory/core.py" store --content "When X, do Y because Z" --tags '["pattern"]'

# Manual feedback with causal filtering (usually automatic via hooks)
python3 "$HELIX/lib/memory/core.py" feedback --names '["name1", "name2"]' --outcome delivered --causal-names '["name1"]'

# Check health (includes causal_ratio metric)
python3 "$HELIX/lib/memory/core.py" health
```

---

## Hook Architecture

| Hook | Trigger | Action |
|------|---------|--------|
| SubagentStop | helix agent completion | Extract insight, apply feedback, write results |
| SessionEnd | session termination | Clean injection-state, remove task-status.jsonl, run decay |

**SubagentStop writes:**
- Explorer: `.helix/explorer-results/{agent_id}.json`
- Builder/Planner: `.helix/task-status.jsonl`

**Feedback is automatic:** When a builder or planner outputs DELIVERED/BLOCKED/PLAN_COMPLETE with INJECTED names, feedback is applied to those insights. Planners participate fully in the feedback loop — their insights compound across sessions just like builders'.

---

## The Deal

Builders handle task-level learning automatically. **You handle session-level learning in LEARN.** Both are required. Close the loop or your next session starts dumber.
