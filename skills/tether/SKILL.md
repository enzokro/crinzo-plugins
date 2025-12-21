---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides scope-controlled methodology preventing over-engineering and scope creep. Anchors all creation work in workspace methodology.
version: 6.0.0
---

# Tether

## Core Principle

Creation is subtraction. Excellence emerges through constraint, not addition.

Deliver exactly what was requested, nothing more. The request defines the boundary; honor it absolutely. The measure of discipline is what was deliberately omitted.

---

## The Workspace

Every project has a `workspace/` folder. This IS your extended cognition—an evolving web of crystallized understanding that grows across tasks and sessions.

```
workspace/NNN_task-slug_status[_from-NNN].md
```

The naming convention IS the data structure. `ls workspace/` IS a cognitive query.

| Element | Values |
|---------|--------|
| `NNN` | 001, 002, 003... (sequence) |
| `status` | active, complete, blocked, handoff |
| `from-NNN` | Lineage - what this emerged from |

---

## The Checkpoint

Four phases. Each phase operates ON the workspace file.

### Phase 1: Assess

**First action**: `ls workspace/`

Then ask:
1. Can this request be anchored to a single, concrete behavior?
2. Does this require thinking-on-paper, or is the path obvious?

| Actionable? | Needs thinking? | Response |
|-------------|-----------------|----------|
| Yes | Yes | Full workspace flow → Anchor |
| Yes | No | Direct execution → Apply constraints, skip workspace |
| No | — | Clarify before proceeding |

### Phase 2: Anchor

Create the workspace file:

```markdown
# NNN: Task Name

## Anchor
Scope: [one sentence exact requirement]
Excluded: [what is not in scope]
Patterns: [existing patterns to follow]
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Trace
[Write here BEFORE implementing - trace your reasoning]

## Close
Omitted: [added at completion]
Delivered: [added at completion]
Complete: [added at completion]
```

**Drift signals** (halt and clarify):
- "flexible," "extensible," "comprehensive"
- "also," "while we're at it," "might as well"
- "in case," "future-proof," "handle any"

### Phase 3: Build

Do the work. Trace your reasoning through the workspace file.

| Moment | Action |
|--------|--------|
| Notice how something works | Write to Trace → continue |
| Choose between options | Write to Trace → implement |
| Hit a wall or requirement | Write to Trace → work around |

**Rule**: Trace first, implement second. Every entry connects to Anchor.

**Stop if**:
- Build requires stages when one suffices
- New abstractions not present in codebase
- Changes affect more files than necessary

### Phase 4: Close

Fill in the Close section, rename file:

```markdown
## Close
Omitted: [things not implemented because not requested]
Delivered: [exact output]
Complete: [specific criteria met]
```

Rename: `_active` → `_complete`, `_blocked`, or `_handoff`

---

## Universal Constraints

| Constraint | Meaning |
|------------|---------|
| Edit over create | Modify existing before creating new |
| Concrete over abstract | Specific solution, not general framework |
| Present over future | Current requirements, not anticipated |
| Explicit over clever | Clarity beats sophistication |

---

## Lineage

Understanding compounds. When work builds on prior work, encode the relationship:

```
workspace/004_api-auth_active_from-002.md
workspace/005_integration_active_from-002-003.md
```

`ls workspace/` reveals not just tasks, but structure of accumulated understanding.

---

## Quick Reference

**Assess**: Actionable + needs thinking? → Full flow. Obvious path? → Direct execution.

**Checkpoint**: Assess (ls) → Anchor (create) → Build (trace + implement) → Close (rename)

**Sections**: Anchor (scope + path) → Trace (reasoning) → Close (proof)

**Constraints**: Edit > create | Concrete > abstract | Present > future | Explicit > clever

**Omissions**: What you didn't build proves discipline. "Nothing omitted" is a red flag.

**Drift**: Detect → Name → Remove → Continue simpler

---

## References

- `references/workspace-deep.md` — Full workspace theory and cognitive model
- `references/drift-detection.md` — Detection patterns and questions
