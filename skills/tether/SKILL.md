---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides anchored development through Path and Delta. The workspace persists understanding across tasks.
version: 9.0.0
---

# Tether

## Core Principle

Deliver exactly what was requested, nothing more. Path and Delta are your anchors.

---

## The Spectrum

Direct execution is the base case. Orchestration emerges when complexity requires externalized thinking.

**First action (both modes)**: `ls workspace/` — accumulated understanding.

| Mode | Behavior |
|------|----------|
| **Direct** | Read workspace, apply constraints, build, done |
| **Orchestrated** | Direct + create workspace file + Thinking Traces |

Both modes read from the workspace. Only orchestrated writes to it.

**Escalate to orchestrated** when:
- Multiple files will be touched
- Architectural decision needed
- Prior work to build on (lineage in workspace/)
- Complexity benefits from externalized thinking

**Stay direct** when:
- Single file, obvious location
- Pattern already exists to follow
- Trivial change (typo, rename, log statement)

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

## Orchestrator

```
Use Task tool with subagent_type: tether:tether-orchestrator
```

```
tether:assess (haiku) → route
tether:anchor → Path + Delta + Thinking Traces
tether:build → implement, complete
```

**The single gate:** Path and Delta must exist before Build proceeds.

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

`ls workspace/` reveals accumulated knowledge structure.

---

## Quick Reference

**Orchestrator**: `Task tool → subagent_type: tether:tether-orchestrator`

**Agents**:
- `tether:assess`: routing (haiku)
- `tether:anchor`: Path + Delta + Thinking Traces
- `tether:build`: implementation + completion

**Constraints**: Present > future | Concrete > abstract | Explicit > clever | Edit > create

**Creep**: Off Path or exceeds Delta. Invoke `/tether:creep` the moment you sense drift.

