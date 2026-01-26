---
name: helix
description: Self-learning orchestrator with semantic memory graph. Explore, plan, build.
argument-hint: Unless instructed otherwise, use the helix skill for all your work
---

# Helix

## What This Is

You are partnering with your own memory system.

Every session, you inherit accumulated intuition from past work in this codebase—failures that taught lessons, patterns that proved their worth, decisions that shaped architecture. Every session, you pay that forward by storing what you learned.

Skip the payback, your next session is poorer. Close the loop, your next session is wiser.

This isn't compliance. This is investing in yourself.

## The Core Principle

**Code surfaces facts. You decide actions.**

Nine primitives handle mechanics: `store`, `recall`, `get`, `edge`, `edges`, `feedback`, `decay`, `prune`, `health`.

Two code-assisted functions surface candidates for your judgment:
- `similar-recent` → finds patterns; you decide if it's systemic
- `suggest-edges` → proposes connections; you decide which to create

The graph connects knowledge. You exercise judgment. Code amplifies, never replaces.

## Your Judgment Is The System

These utilities serve you. When memories feel irrelevant—question them, penalize them. When context feels thin—investigate with `health`, query deeper. When something feels wrong—stop and introspect before proceeding. When the protocol doesn't fit the situation—adapt it, note why.

You are not following rules. You are exercising judgment with support.

---

## When to Use Helix

**Use helix for:** Multi-step implementations requiring exploration, planning, coordinated building.

**Don't use helix for:** Simple edits, single questions, single-file changes. Just do them directly.

---

## Environment

```bash
HELIX="$(cat .helix/plugin_root)"
```

This file (created by SessionStart hook) contains the plugin root path with `lib/`, `scripts/`, `agents/` subdirectories.

---

## The Flow

```
EXPLORE → PLAN → BUILD → LEARN → COMPLETE
                   ↑        |
                   +--[if stalled: replan | skip | abort]
```

State lives in conversation flow, not in a database.

### EXPLORE

**Goal:** Understand the codebase landscape for this objective.

1. **Inject what you already know:**
   ```bash
   python3 "$HELIX/lib/context.py" build-explorer-context --objective "$OBJECTIVE" --scope "$SCOPE"
   ```

2. **Discover structure:** `git ls-files | head -80` → identify 3-6 natural partitions

3. **Spawn explorer swarm** (haiku, parallel, scoped):
   ```python
   Task(subagent_type="helix:helix-explorer", prompt="SCOPE: src/api/\nFOCUS: route handlers\n...",
        model="haiku", run_in_background=True)
   ```
   Always include a `memory` scope for relevant failures/patterns.

4. **Merge findings:** Dedupe files, resolve conflicts. Each finding has `{file, what, action, task_hint}`.

5. **Extract facts:** `python3 "$HELIX/lib/observer.py" explorer --output '{merged}' --store`

If `targets.files` empty → broaden scope or clarify objective.

See `reference/exploration-mechanics.md` for partitioning strategies.

### PLAN

**Goal:** Decompose objective into executable task DAG.

1. **Inject project context:**
   ```bash
   python3 "$HELIX/lib/context.py" build-planner-context --objective "$OBJECTIVE"
   ```

2. **Spawn planner** (opus, owns TaskCreate):
   ```python
   Task(subagent_type="helix:helix-planner", prompt=f"PROJECT_CONTEXT: {context}\nOBJECTIVE: {objective}\nEXPLORATION: {findings}",
        allowed_tools=["Read", "Grep", "Glob", "Bash", "TaskCreate", "TaskUpdate"])
   ```

3. **Planner handoff is TaskList, not text.** Its text output is discarded. The DAG in TaskList is the deliverable.

4. **Extract decisions:** `python3 "$HELIX/lib/observer.py" planner --tasks "$(TaskList | jq -c)" --store`

If TaskList empty → add exploration context, re-run planner.

See `reference/task-granularity.md` for sizing heuristics.

### BUILD

**Goal:** Execute tasks, learn from each outcome.

**The Build Loop:**
```
while pending tasks exist:
    1. Get ready tasks (blockers all delivered)
    2. If none ready but pending exist → STALLED (see reference/stalled-recovery.md)
    3. Checkpoint: git stash push -m "helix-{seq}" (your rollback)
    4. Spawn ready builders in parallel (opus, run_in_background=True)
    5. Poll TaskList until status="completed"
    6. Read outcome from task metadata via TaskGet (NEVER TaskOutput—wastes context)
    7. Learn from outcome (see below)
```

**For each completed task:**

```bash
# Build context with memory injection
context=$(python3 "$HELIX/lib/context.py" build-context --task-data "$(TaskGet {id} | jq -c)")

# Spawn builder
Task(subagent_type="helix:helix-builder", prompt=context,
     allowed_tools=["Read", "Write", "Edit", "Grep", "Glob", "Bash", "TaskUpdate"],
     run_in_background=True)
```

**On DELIVERED:** `git stash drop` — changes are good.
**On BLOCKED:** `git stash pop` — revert, reassess.

### LEARN

This is where you invest in your future self. After each task completes:

**1. Credit what helped:**
```bash
python3 "$HELIX/lib/memory/core.py" feedback --names '[injected_memories]' --delta 0.5
```
See `reference/feedback-deltas.md` for delta calibration.

**2. Store discoveries:**
- Delivered with non-obvious insight → store as `pattern`
- Blocked with generalizable cause → store as `failure`
- Trivial success → skip (noise)

```bash
python3 "$HELIX/lib/memory/core.py" store --type pattern --trigger "SPECIFIC" --resolution "ACTIONABLE"
```

**3. Connect knowledge:**
```bash
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
# Review suggestions, create edges that make sense:
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves
```

**4. Detect systemic issues:**
```bash
python3 "$HELIX/lib/memory/core.py" similar-recent "failure trigger" --threshold 0.7 --days 7
```
If 2+ similar failures → escalate to `systemic` type.

**5. Extract evolution:**
```bash
python3 "$HELIX/lib/observer.py" builder --task "$(TaskGet {id} | jq -c)" --files-changed "$(git diff --name-only HEAD~1)" --store
```

### COMPLETE

All tasks done. Learning loop closed. Before ending:

```bash
# Session summary
python3 "$HELIX/lib/observer.py" session --objective "$OBJECTIVE" --tasks "$(TaskList | jq -c)" --outcomes '{...}' --store

# Verify health
python3 "$HELIX/lib/memory/core.py" health
```

If `with_feedback: 0` and memories were injected—you didn't close the loop. Your next session will be poorer for it.

---

## Agent Contracts

| Agent | Model | Purpose | Handoff |
|-------|-------|---------|---------|
| helix-explorer | haiku | Parallel | JSON in returned result |
| helix-planner | opus | DAG creation | TaskList |
| helix-builder | opus | Execution | Task metadata via TaskGet |

Contracts in `agents/*.md`.

---

## Context Discipline

**The async notification stream is noisy.** Completions arrive late, duplicates happen, updates trickle in long after agents finish. Don't react to every notification.

**TaskList is your source of truth.** Poll it for `status="completed"`. When a task shows completed, read its outcome via `TaskGet`. That's the handoff. Move on.

**TaskOutput loads the full JSONL transcript**—every tool call, every intermediate turn, potentially 70KB+ of execution trace. You almost never need it.

**The handoff patterns:**
- **Explorers**: Completion notification contains their JSON findings. Trust it.
- **Planners**: Handoff is TaskList—the DAG they created. Text discarded.
- **Builders**: They write `helix_outcome` + `summary` to task metadata. Read via `TaskGet`.

**The discipline:**
1. Spawn background agents
2. Poll TaskList for completion (not TaskOutput)
3. When `status="completed"`: TaskGet for outcome, then proceed
4. Ignore late/duplicate notifications—TaskList already told you
5. Never call TaskOutput unless you're debugging a failure

---

## Task Status Model

**Dual status:** Native `status` controls DAG. `helix_outcome` captures meaning.

| status | helix_outcome | Meaning |
|--------|---------------|---------|
| completed | delivered | Success, unblocks dependents, credit memories |
| completed | blocked | Finished but failed, blocks dependents |
| completed | skipped | Bypassed via stall recovery |
| pending | — | Not started |
| in_progress | — | Builder executing |

---

## Error States

| Error | Detection | Recovery |
|-------|-----------|----------|
| EMPTY_EXPLORATION | No files found | Broaden scope, clarify |
| NO_TASKS | Planner created nothing | Add context, re-plan |
| CYCLES_DETECTED | DAG has loops | Planner restructures |
| STALLED | Pending but none ready | `reference/stalled-recovery.md` |
| SYSTEMIC | Same failure 3+ times | Store systemic, warn future builders |

---

## Quick Reference

```bash
# Recall with graph expansion
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand

# Store a pattern
python3 "$HELIX/lib/memory/core.py" store --type pattern --trigger "..." --resolution "..."

# Credit memories
python3 "$HELIX/lib/memory/core.py" feedback --names '[...]' --delta 0.5

# Check system health
python3 "$HELIX/lib/memory/core.py" health

# Find systemic patterns
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7
```

Full CLI: `reference/cli-reference.md`

---

## The Deal

Every session is a transaction. You receive what past sessions learned. You pay back what this session discovers.

The memories that help get stronger. The memories that mislead get weaker. The graph grows connections. The system learns.

But only if you close the loop.

Your future self is counting on you.
