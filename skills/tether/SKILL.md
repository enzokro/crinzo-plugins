---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides scope-controlled methodology preventing over-engineering and scope creep. Anchors all creation work in workspace methodology.
version: 8.0.0
---

# Tether

## Core Principle

Creation is subtraction. Excellence emerges through constraint, not addition.

Deliver exactly what was requested, nothing more. The request defines the boundary; honor it absolutely. The measure of discipline is what was deliberately omitted.

---

## Orchestrated Execution

**For full workspace flow, invoke the orchestrator:**

```
Use Task tool with subagent_type: tether:tether-orchestrator
```

The orchestrator coordinates four phase agents with contract verification between each:

```
[Assess] → route → [Anchor] → file+T1 → [Build] → T2,T3+ → [Close] → complete
     ↓                  ↓                    ↓                  ↓
  haiku            verify T1           verify T2,T3      verify Omitted
```

Each agent boundary is a contract boundary. The orchestrator verifies artifacts exist before spawning the next phase. This is structural enforcement, not self-discipline.

**When to use orchestrator:**
- Complex, multi-step implementations
- Work requiring decision traces
- Tasks where scope discipline matters

**When to execute directly:**
- Simple, obvious changes
- Single-file edits
- Following existing patterns exactly

For direct execution, apply the constraints below manually.

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

Four phases. Each phase is a cognitive operation that produces an artifact for the next.

```
Assess → [routing decision] → Anchor → [workspace file + T1] → Build → [T2, T3...] → Close
```

### Phase 1: Assess

**Input**: User request
**Output**: Routing decision (full flow / direct / clarify)

**First action**: `ls workspace/`

Then ask:
1. Can this request be anchored to a single, concrete behavior?
2. Does this require thinking-on-paper, or is the path obvious?

| Actionable? | Needs thinking? | Route to |
|-------------|-----------------|----------|
| Yes | Yes | → Anchor (full flow) |
| Yes | No | → Build (direct, skip workspace) |
| No | — | → User (clarify first) |

### Phase 2: Anchor

**Input**: User request + routing decision
**Output**: Workspace file with Anchor section + T1 checkpoint

Create the workspace file. T1 is filled HERE, not in Build—it captures initial understanding before implementation begins:

```markdown
# NNN: Task Name

## Anchor
Scope: [one sentence exact requirement]
Excluded: [what is not in scope]
Patterns: [existing patterns to follow]
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Trace
### T1: [filled at Anchor—initial understanding, patterns found, approach]
### T2: [filled at Build—after first implementation step]
### T3: [filled at Build—before closing]

## Close
Omitted: [added at Close]
Delivered: [added at Close]
Complete: [added at Close]
```

**Contract**: Anchor phase MUST fill T1 before handing off to Build. T1 captures what was learned during exploration—patterns found, approach chosen, constraints identified. This is the decision trace that informs implementation.

### Phase 3: Build

**Input**: Workspace file with Anchor section + T1 filled
**Output**: T2, T3+ checkpoints filled; implementation complete

Do the work. Think ON the workspace file, not in your head.

**The Pairing Rule**: Every TodoWrite update pairs with a Trace write. You will update TodoWrite—that's your locked-in pattern. Use it. When you update TodoWrite, also write to Trace. They move together.

**Checkpoints during Build**:
- **T2**: After first implementation step completes
- **T3+**: Add more as needed—after each significant decision or discovery

If a checkpoint is empty when you move past it, stop. Fill it in. The structure makes staleness visible.

| Moment | Action |
|--------|--------|
| Update TodoWrite | Also write to Trace (pairing rule) |
| Notice how something works | Write to Trace → continue |
| Choose between options | Write to Trace → implement |
| Hit a wall or requirement | Write to Trace → work around |
| Sense complexity growing | Run `/tether:creep` → check against Anchor |

**Rule**: Trace first, implement second. Every entry connects to Anchor.

**Creep signals** (stop and check):
- "flexible," "extensible," "comprehensive"
- "while we're at it," "also," "and"
- "in case," "future-proof"
- Empty Trace section during active work

**Stop if**:
- Build requires stages when one suffices
- New abstractions not present in codebase
- Changes affect more files than expected

### Phase 4: Close

**Input**: Workspace file with Anchor + T1, T2, T3+ filled; implementation complete
**Output**: Completed workspace file; renamed to final status

**Contract verification** (gate check):
1. T1 filled (from Anchor phase)
2. T2, T3 filled (from Build phase)
3. Each Trace entry connects to Anchor
4. Omitted list will be non-empty

If contract fails: phase cannot complete. Go back and fill in what's missing.

Fill in the Close section:

```markdown
## Close
Omitted: [things not implemented because not requested—this MUST be non-empty]
Delivered: [exact output matching Anchor scope]
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

**Orchestrator**: `Task tool → subagent_type: tether:tether-orchestrator`

**Phase Flow** (orchestrated):
```
[Assess] → route → [Anchor] → file+T1 → [Build] → T2,T3+ → [Close]
    ↓                  ↓                    ↓                  ↓
 haiku           verify T1           verify T2,T3      verify Omitted
```

**Agents**:
- `tether:assess` — routing decision (haiku)
- `tether:anchor` — workspace file + T1
- `tether:code-builder` — implementation + T2, T3+
- `tether:close` — verification + completion (haiku)

**Contracts** (verified by orchestrator):
- Anchor → Build: T1 must have substantive content
- Build → Close: T2, T3 must have substantive content
- Close gate: Omitted must be non-empty

**Pairing Rule** (during Build): Every TodoWrite update pairs with a Trace write.

**Constraints**: Edit > create | Concrete > abstract | Present > future | Explicit > clever

**Creep**: Sense it → `/tether:creep` → Name it → Remove it → Continue simpler

---

## References

**Agents** (in `agents/`):
- `tether-orchestrator.md` — Phase coordination with contract verification
- `assess.md` — Routing phase (haiku)
- `anchor.md` — Scoping phase
- `code-builder.md` — Build phase
- `close.md` — Completion phase (haiku)

**Deep Dives** (in `references/`):
- `workspace-deep.md` — Workspace theory and cognitive model
- `creep-detection.md` — Scope creep patterns and detection
