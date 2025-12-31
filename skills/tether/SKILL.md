---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides tiered and anchored development preventing over-engineering and scope creep. The workspace and externalized traces drive tether's workflow.
version: 8.1.0
---

# Tether

## Core Principle

Deliver exactly what was requested, nothing more. The request defines your boundary.

Constraints drive excellence. Creation is subtraction via disciplined omission, not spastic addition.

---

## The Spectrum

Direct execution is the base case. Orchestration emerges when complexity requires accountability.

**First action (both modes)**: `ls workspace/` — crystallized knowledge for higher-order thinking.

| Mode | Behavior |
|------|----------|
| **Direct** | Read workspace, apply constraints, build, done |
| **Orchestrated** | Direct + create workspace file + traces |

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

**Implicit escalation**: If complexity emerges mid-execution, escalate. But bias towards completing direct if initially routed there.

---

## Universal Constraints

| Constraint | Meaning |
|------------|---------|
| **Present over future** | Current request, not anticipated needs |
| **Concrete over abstract** | Specific solution, not framework |
| **Explicit over clever** | Clarity over sophistication |
| **Edit over create** | Modify existing before creating new |

Do NOT create new abstractions. Do NOT touch files outside the request's scope.

---

## Orchestrator

```
Use Task tool with subagent_type: tether:tether-orchestrator
```

```
tether:assess (haiku) -> route
tether:anchor -> file+T1 (Path/Delta established)
tether:code-builder -> T2,T3+ (Path followed)
tether:close (haiku) -> complete
```

Path and Delta guide all decisions.

---

## The Workspace

Every project has a `workspace/` folder. It IS your extended cognition — distilled knowledge that compounds across tasks.

```
workspace/NNN_task-slug_status[_from-NNN].md
```

`ls workspace/` becomes a cognitive query. The naming convention IS the data structure.

| Element | Purpose |
|---------|---------|
| `NNN` | Sequence (001, 002...) |
| `status` | active, complete, blocked, handoff |
| `from-NNN` | Lineage — what this emerged from |

For workspace file structure and protocols, see agent files.

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
- `tether:anchor`: scope + T1
- `tether:code-builder`: implementation + T2,T3+
- `tether:close`: verification (haiku)

**Constraints**: Present > future | Concrete > abstract | Explicit > clever | Edit > create

**Creep**: Off Path or exceeds Delta → `/tether:creep` → Reflect → Correct

---

## References

**Agents** (in `agents/`): Detailed protocols for each phase
**Deep Dives** (in `references/`): workspace-deep.md, creep-detection.md
