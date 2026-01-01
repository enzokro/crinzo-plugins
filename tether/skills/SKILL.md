---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides anchored development through Path and Delta. The workspace persists understanding across tasks.
version: 9.1.0
---

# Tether

## Core Principle

Deliver exactly what was requested, nothing more. Path and Delta are your anchors.

---

## First Action

**Always invoke the orchestrator:**

```
Task tool with subagent_type: tether:tether-orchestrator
```

Pass through the user's request. The orchestrator handles routing internally via assess.

Do NOT make routing decisions yourself. Do NOT implement directly. Invoke orchestrator, then step back.

---

## What Happens Inside

The orchestrator runs four phases:

```
tether:assess (haiku) → route
tether:anchor → Path + Delta + Thinking Traces
tether:build → implement, complete
tether:reflect → extract patterns (conditional)
```

**Assess routes to:**
- `full` → Anchor creates workspace file, then Build implements
- `direct` → Build with constraints only (read workspace, no new file)
- `clarify` → Return question to user, halt

**The single gate:** Path and Delta must exist before Build proceeds.

---

## Universal Constraints

| Constraint | Meaning |
|------------|---------|
| **Present over future** | Current request, not anticipated needs |
| **Concrete over abstract** | Specific solution, not framework |
| **Explicit over clever** | Clarity over sophistication |
| **Edit over create** | Modify existing before creating new |

Do NOT create new abstractions. Do NOT touch files outside the Delta.

---

## The Workspace

Every project has a `workspace/` folder. It IS your extended cognition.

```
workspace/NNN_task-slug_status[_from-NNN].md
```

`ls workspace/` becomes a cognitive query. The naming convention IS the data structure.

| Element | Purpose |
|---------|---------|
| `NNN` | Sequence (001, 002...) |
| `status` | active, complete, blocked |
| `from-NNN` | Lineage — what this emerged from |

### Workspace File Structure

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Thinking Traces
[externalized thinking—exploration, decisions, pen and paper]

## Delivered
[filled at completion]
```

---

## Lineage

Understanding compounds. When work builds on prior work, encode the relationship:

```
workspace/004_api-auth_active_from-002.md
```

`ls workspace/` reveals the knowledge graph. Query patterns with grep:

```bash
grep -h "^#pattern/\|^#constraint/\|^#decision/" workspace/*_complete*.md | sort -u
```

---

## Quick Reference

**Orchestrator**: `Task tool → subagent_type: tether:tether-orchestrator`

**Agents**:
- `tether:assess`: routing (haiku)
- `tether:anchor`: Path + Delta + Thinking Traces
- `tether:build`: implementation + completion
- `tether:reflect`: pattern extraction (conditional)

**Constraints**: Present > future | Concrete > abstract | Explicit > clever | Edit > create

**Creep**: Off Path or exceeds Delta. Invoke `/tether:creep` the moment you sense drift.

---

## Agent Constraints

All agents follow the universal constraints above. Each phase also has boundary discipline:

| Principle | Meaning |
|-----------|---------|
| **Stay in lane** | Each phase does its job, nothing more |
| **No forward reach** | Don't do work that belongs to a later phase |
| **No backward reach** | Don't redo work that a prior phase completed |

### Phase Boundaries

```
Assess: route only     --> Anchor: plan only     --> Build: implement only
        |                         |                         |
        v                         v                         v
   No exploring              No implementing          No re-planning
   No creating files         No skipping Traces       No new abstractions
   No implementing           No over-scoping          Stay within Delta
```

Each agent references these shared constraints, then adds phase-specific rules.

---

## Configuration

Settings live in `tether/config.md`. Edit to customize behavior.

| Setting | Default | Purpose |
|---------|---------|---------|
| `workspace_path` | `workspace/` | Where task files are stored |
| `sequence_padding` | `3` | Digits in sequence numbers (3 = 001) |
| `default_route` | `full` | Fallback when assess is uncertain |
| `assess_model` | `haiku` | Model for routing phase |
| `build_model` | `inherit` | Model for anchor/build phases |

