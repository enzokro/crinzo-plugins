---
name: tether
description: Use when the user asks to create, build, implement, write, design, plan, generate, draft, make, add a feature, or develop. Provides tiered and anchored development preventing over-engineering and scope creep. The workspace and externalized traces drive tether's workflow.
version: 8.0.0
---

# Tether

## Core Principle

Deliver exactly what was requested, nothing more. The request defines your boundary and constraints. 

Constraints drive excellence. A focused scope, over time, compounds into exponential results. Creation is subtraction via disciplined omission, not spastic addition.

---

## Orchestrated Execution

**For full workspace flow, invoke the orchestrator:**

```
Use Task tool with subagent_type: tether:tether-orchestrator
```

The orchestrator coordinates four tiered agents with verified contracts between them:

```
tether:assess (haiku) -> route
tether:anchor -> file+T1 [gate: T1]
tether:code-builder -> T2,T3+ [gate: T2,T3]
tether:close (haiku) -> complete [gate: Omitted≠∅]
```

Each agent handoff is gated by a contractually verified trace. The orchestrator checks that traces exist before starting its next agent. This is structural enforcement, not self-discipline.

**When to use orchestrator:**
- Complex implementations with multiple steps
- Tasks where focused, scoped discipline matters
- Challenging requests that benefit from externalized thinking traces

**When to execute directly:**
- Simple, obvious changes
- Direct edits to single files
- Mimicking an existing pattern

For direct execution, apply the constraints below manually.

---

## The Workspace

Every project has a `workspace/` folder. The workspace IS your extended cognition. It is an evolving store of distilled, long-term knowledge that weaves across tasks and sessions.

```
workspace/NNN_task-slug_status[_from-NNN].md
```

The naming convention IS the data structure. `ls workspace/` becomes a cognitive query:

| Element    | Values                             |
| ---------- | ---------------------------------- |
| `NNN`      | 001, 002, 003... (sequence)        |
| `status`   | active, complete, blocked, handoff |
| `from-NNN` | Lineage - what this emerged from   |

---

## Tiered Agent Handoff

Each tiered, focused agent performs a constrained task that generates traces for the next agent. The orchestrator confirms the needed traces exist before starting the next agent.

### Phase 1: `tether:assess`

**Input**: User request
**Output**: Routing decision (full flow / direct / clarify)

**First action**: `ls workspace/`

Then ask:
1. Is this request tied to a single, concrete behavior?
2. Does this need externalized workspace thinking, or is the path obvious?

| Actionable? | Needs thinking? | Route to                         |
| ----------- | --------------- | -------------------------------- |
| Yes         | Yes             | → Anchor (full flow)             |
| Yes         | No              | → Build (direct, skip workspace) |
| No          | —               | → User (clarify first)           |

### Phase 2: `tether:anchor`

**Input**: User request + routing decision
**Output**: Workspace file with Anchor section + T1 trace

Create the workspace file. T1 is filled HERE, before we Build: it scopes the initial understanding that will guide implementation:

```markdown
# NNN: Task Name

## Anchor
Scope: [one sentence exact requirement]
Excluded: [what is not in scope]
Patterns: [existing patterns to follow]
Data Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Trace
### T1: [`tether:anchor` fills: patterns found, approach, references Path]
### T2: [`tether:code-builder` fills: after first step, references Anchor]
### T3: [`tether:code-builder` fills: significant decision, references Anchor]

## Close
Omitted: [added at Close]
Delivered: [added at Close]
Complete: [added at Close]
```

**Contract**: Anchor phase MUST fill T1 before handing off to Build. T1 captures what was learned during exploration: patterns found, constraints identified, approaches chosen. This is the decision trace that informs implementation.

### Phase 3: `tether:code-builder`

**Input**: Workspace file with Anchor section + T1 filled
**Output**: T2, T3+ traces filled, complete implementation

Do the work. Writes Traces *during* implementation, in lockstep with meaningful TodoWrite tool calls.
Build phase is where the Workspace shines as external, long-term crystallized knowledge. The agent leverages the workspace as pen-and-paper for higher-order thinking.

**Execution Protocol**:
1. Read workspace file: verify T1 has informative anchor content
2. Confirm Anchor's path is still correct
3. Execute in minimal, elegant increments
4. **Fill T2 immediately** after first implementation step
5. **Fill T3+** after each significant decision or discovery
6. **Pairing Rule**: TodoWrite tool calls must lead to a Trace write

**Connection Requirement**: Each Trace must reference the Anchor explicitly:
- Which part of **Data Path** does this advance?
- Which **Excluded** items are you deliberately avoiding?
- Are we within **Scope** and **Delta**?

| Moment                  | Action                                     |
| ----------------------- | ------------------------------------------ |
| First step done         | Write T2 → reference Anchor path           |
| Made a decision         | Write T3+ → reference Anchor constraints   |
| Update TodoWrite        | Also write to Trace (pairing rule)         |
| Can't connect to Anchor | Stop → you've drifted, reassess            |
| Complexity growing      | Run `/tether:creep` → check against Anchor |

If you can't connect what you're doing to Scope/Path/Delta/Excluded, you've drifted. Stop and reassess.
Call the `tether:anchor` agent again with explicit instructions to refactor the Anchor to align with your current work.

**Creep signals** (stop and check):
- "flexible," "extensible," "comprehensive"
- "while we're at it," "also," "and"
- "in case," "future-proof"
- Empty Trace section during active work

**Stop if**:
- Build requires stages when one suffices
- New abstractions not present in codebase
- Changes affect more files than expected

### Phase 4: `tether:close`

**Input**: Workspace file with Anchor + Traces filled. Implementation complete.
**Output**: Final workspace file, renamed to current status

**Contract verification** (gate check):
1. T1 filled (from Anchor phase)
2. T2, T3+ filled (from Build phase)
3. Each Trace entry connects to Anchor
4. Omitted list must be non-empty

If contract fails: phase cannot complete. Go back and fill in what's missing.
Call the appropriate agents with context about what failed to fix the Traces and re-run.

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

| Constraint                 | Meaning                                                   |
| -------------------------- | --------------------------------------------------------- |
| **Present over future**    | Implement current requests, not future anticipated needs. |
| **Concrete over abstract** | Build a specific solution, not abstract frameworks.       |
| **Explicit over clever**   | Always choose clarity over sophistication.                |
| **Edit over create**       | Modify what exists before creating something new.         |

---

## Lineage

Understanding compounds over tasks and sessions in the Workspace.
When we build on previous efforts, encode the relationship:

```
workspace/004_api-auth_active_from-002.md
workspace/005_integration_active_from-002-003.md
```

`ls workspace/` reveals not just tasks, but the structure of accumulated knowledge.

---

## Quick Reference

**Orchestrator**: `Task tool → subagent_type: tether:tether-orchestrator`

**Phase Flow** (orchestrated):
```
tether:assess (haiku) -> route
tether:anchor -> file+T1 [gate: T1]
tether:code-builder -> T2,T3+ [gate: T2,T3]
tether:close (haiku) -> complete [gate: Omitted≠∅]
```

**Agents**:
- `tether:assess`: routing decision (haiku)
- `tether:anchor`: workspace file + T1
- `tether:code-builder`: implementation + T2, T3+
- `tether:close`: verification + completion (haiku)

**Contracts** (verified by orchestrator):
- Anchor → Build: T1 must have informative anchor content
- Build → Close: T2, T3 must have informative implementation content
- Close gate: Omitted must be non-empty

**Pairing Rule**: Every TodoWrite update pairs with a Trace write.

**Connection Requirement**: Each Trace entry must reference Anchor (Path/Scope/Delta/Excluded).

**Constraints**: Present > future | Concrete > abstract | Explicit > clever | Edit > create

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
