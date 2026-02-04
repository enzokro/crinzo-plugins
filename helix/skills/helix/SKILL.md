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

Six primitives handle memory mechanics: `store`, `recall`, `get`, `feedback`, `decay`, `prune`, `health`.

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

1. **Discover structure:** `git ls-files | head -80` → identify 3-6 natural partitions

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

3. **Wait for results** (SubagentStop hook writes findings to files):
   ```bash
   while [ $(ls .helix/explorer-results/*.json 2>/dev/null | wc -l) -lt $EXPLORER_COUNT ]; do
     sleep 2
   done
   ```

4. **Merge findings:**
   ```bash
   cat .helix/explorer-results/*.json | jq -s '[.[].findings // []] | add | unique_by(.file)'
   ```

5. **Cleanup:**
   ```bash
   rm -rf .helix/explorer-results/
   ```

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

Get relevant insights for the task:

```python
from lib.injection import inject_context

context = inject_context(task_objective, limit=5)
# context = {"insights": ["[75%] When X...", ...], "names": ["insight-name-1", ...]}
```

Or via CLI:
```bash
python3 -c "from lib.injection import inject_context; import json; print(json.dumps(inject_context('$OBJECTIVE', 5)))"
```

Include in builder prompt:
```
TASK_ID: {task_id}
TASK: {task_subject}
OBJECTIVE: {task_description}
VERIFY: {verification_steps}
RELEVANT_FILES: {files}

INSIGHTS (from past experience):
  - [75%] When implementing auth, check token expiry first
  - [60%] Use dependency injection for testability

INJECTED: ["insight-name-1", "insight-name-2"]
```

The `INJECTED` line enables feedback attribution when the builder completes.

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

Poll `.helix/task-status.jsonl` for completion:
```bash
cat .helix/task-status.jsonl 2>/dev/null
```

#### Build Loop

```
while pending tasks exist:
    1. Get ready tasks (blockers all completed)
    2. If none ready but pending exist → STALLED
    3. Checkpoint: git stash push -m "helix-{seq}"
    4. Spawn ready builders (inject insights first)
    5. Process results, update task status
```

**On DELIVERED:** `git stash drop` — changes are good.
**On BLOCKED:** `git stash pop` — revert, reassess.

#### Automatic Builder Learning

The SubagentStop hook automatically:
1. Extracts INSIGHT from builder output (if present)
2. Stores new insight to memory
3. Applies feedback to INJECTED insights based on outcome

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

- `with_feedback > 0` if insights were injected (builders provided outcomes)
- `total_insights` increased if LEARN phase stored discoveries

If you injected insights and `with_feedback: 0`, something broke. If the session completed work and you stored nothing in LEARN, you wasted knowledge.

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
# Recall insights
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5

# Store new insight
python3 "$HELIX/lib/memory/core.py" store --content "When X, do Y because Z" --tags '["pattern"]'

# Manual feedback (usually automatic via hooks)
python3 "$HELIX/lib/memory/core.py" feedback --names '["name1", "name2"]' --outcome delivered

# Check health
python3 "$HELIX/lib/memory/core.py" health
```

---

## Hook Architecture

| Hook | Trigger | Action |
|------|---------|--------|
| SubagentStop | helix agent completion | Extract insight, apply feedback, write results |

**SubagentStop writes:**
- Explorer: `.helix/explorer-results/{agent_id}.json`
- Builder: `.helix/task-status.jsonl`

**Feedback is automatic:** When builder outputs DELIVERED/BLOCKED with INJECTED names, feedback is applied to those insights.

---

## The Deal

You receive accumulated knowledge. You pay back discoveries.

Builders handle task-level learning automatically. **You handle session-level learning manually.** Both are required.

Insights that help get stronger. Insights that mislead get weaker.

**Close the loop or your next session starts dumber than this one ended.**
