# `tether`

`tether` is a Claude Code agent orchestrator for clean and focused development. It builds on the step function jump in agentic coding capabilities unlocked by Opus 4.5.

## Background

Before Opus 4.5, Agents dedicated many of their prompts and tools to working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding assistants behaved like overeager Junior-savants that had to be carefully steered whenever projects grew even moderately complex.

Opus 4.5 broke this pattern. If you're reading this then you've likely felt the shift. Talking to Opus 4.5, it *gets* it. The ineffable *it*. We are now living the transformation of LLM Agents from spastic assistants to powerful, intelligent collaborators.

`tether` combines the model's increased capabilities *and* their better understanding of our needs into a powerful development harness. Its orchestrator guides sub-agents along tiered phases with stable constraints that externalize their thinking over sessions. And all of this fully anchored on Opus 4.5; no more cautious model handholding.

# Philosophy

`tether` is based on four principles to keep Agents focused on the task at hand:

| Principle                  | Description                                               |
| -------------------------- | --------------------------------------------------------- |
| **Present over future**    | Implement current requests, not anticipated future needs. |
| **Concrete over abstract** | Build a specific solution, not abstract frameworks.       |
| **Explicit over clever**   | Always choose clarity over sophistication.                |
| **Edit over create**       | Modify what exists before creating something new.         |

None of these are new. In fact they read as the obvious 101s of software development. But anyone who's spent time building apps with LLMs knows that the models are ambitious and like to stay busy. They often deviate from these principles and tech debt quickly accumulates, especially in complex projects. `tether` gives Claude Code a framework that makes these principles its north star. 

# Installation

Add the tether plugin to your marketplace and install it.
```bash
claude /plugin install <your-marketplace>/tether
```

Make sure to update the marketplace.json file to include the plugin.


# Architecture

`tether` follows a development cycle with four phases. Each phase is delegated to an agent with bounded context. The orchestrator then checks that each agent created the proper, structured Trace (T) artifacts before spawning its next phase. For complex tasks, the orchestrator chronicles its process in a workspace file. This is a key part of `tether`'s workflow and we describe it more in the next section. First, a look at the main development cycle:

```
[Assess] → route → [Anchor] → file+T1 → [Build] → T2,T3+ → [Close]
    ↓                  ↓                    ↓                  ↓
 decide            verify T1           verify T2,T3      verify Omitted
```

Next, let's look at the agents that make up `tether`:

## Tether Agents

| Agent                        | Purpose                                             | Model   |
| ---------------------------- | --------------------------------------------------- | ------- |
| `tether:tether-orchestrator` | Coordinates phases, verifies contracts              | inherit |
| `tether:assess`              | Routing decision                                    | haiku   |
| `tether:anchor`              | Creates workspace file, explores codebase, fills T1 | inherit |
| `tether:code-builder`        | Implementation with T2/T3+ decision traces          | inherit |
| `tether:close`               | Verifies contracts, fills Close, renames file       | haiku   |

Decision traces `T*` are a key part of how `tether` stays focused on the user's actual request. 

## Decision Traces

Traces `T*` are where reasoning becomes visible and auditable. Each step must reference the Anchor to keep the model well-scoped in complex tasks.

- **T1** (Anchor fills): Patterns found, approach chosen, references Path
- **T2** (Build fills): After first implementation step, references Anchor
- **T3+** (Build fills): Significant decisions during implementation, each references Anchor

With both the Agents and Traces established, we can look at how they interact during `tether`'s workflow.

## Phase 1: Assess

The `assess` Agent decides whether we are dealing with a simple ask that can be done ad hoc or a complex task that requires more deliberation. In other words, can the user's request be anchored to a single, concrete action with an obvious path? Or, do we need `tether`'s full workflow?

| Actionable? | Needs thinking? | Route to           |
| ----------- | --------------- | ------------------ |
| Yes         | Yes             | Anchor (full flow) |
| Yes         | No              | Build (direct)     |
| No          | —               | User (clarify)     |

## Phase 2: Anchor

The `anchor` Agent defines the request's scope, explores the codebase for patterns, and, crucially, decides what the model will *not* do.

**Contract**: The Agent must fill T1 before the `build` Agent does any work. T1 captures what was learned during exploration: codebase patterns, potential approaches, and key constraints. This is the minimal, data-driven Trace that informs implementation.

## Phase 3: Build

The `build` Agent implements what the Anchor defines, nothing more and nothing less. The workspace file acts as a cognitive surface. Thinking must happen in the workspace and not in a jumble of internal thinking traces.

**The Connection Constraint**: Every Trace entry *must* reference the Anchor. The model is not allowed to say "I did X". Instead, it must say: "I did X, advancing Path step 2, avoiding Y per Excluded." If the connection breaks, the model stops, re-anchors, and tries again. 

It must be said here that Claude Code's ToDo harness is incredibly powerful. The model strongly resists work loops that are anything but a series of TodoWrite <-> Thinking iterations. To overcome this, we enforce a **Pairing Rule**: Every `TodoWrite` update pairs with a Trace write. TodoWrite tracks *what* was done, while the Trace captures *why*. `tether` helps them move in lockstep.

| Step               | Reaction                                   |
| ------------------ | ------------------------------------------ |
| First step done    | Fill T2, reference Anchor path             |
| Decision made      | Fill T3+, reference Anchor constraints     |
| TodoWrite updated  | Also write to Trace                        |
| Connection breaks  | Stop → drift detected → reassess           |
| Complexity growing | Run `/tether:creep` → check against Anchor |

## Phase 4: Close

The `close` Agent verifies all contracts, fills the Close section, and renames the workspace file to its final status. Further, `close` cannot proceed unless T1, T2, and T3+ are filled. Each Trace entry must connect back to Anchor. And Omitted must contain deliberate exclusions—not oversights, but choices. The measure of discipline is what was left out on purpose.

This is where discipline becomes visible. We fight the model's helpful but misaligned urge to implement everything they can think of and call it thoroughness. `tether` fights this: the Omitted section *must* be non-empty. If the model delivered everything and omitted nothing, scope crept in somewhere.

## Tether Commands (for manual and ad hoc interventions)

| Command                 | Purpose                              |
| ----------------------- | ------------------------------------ |
| `/tether:workspace`     | Query active tasks and their lineage |
| `/tether:anchor [task]` | Manually create a workspace file     |
| `/tether:close [task]`  | Manually complete a task             |
| `/tether:creep`         | Check for scope creep during Build   |


# The Workspace: Externalized Knowledge Across Sessions

`tether` builds on this agentic paradigm shift with a Workspace. Workspaces are the linked, evolving record of a project's scope, decisions, and implementations. They are built from structured markdown files with a naming convention inspired by Herbert A. Simon's List of Lists. We created them in this spirit to represent knowledge and action in constrained environments. And, critically, they persist across sessions.

## Workspace File Structure

`tether` guides complex tasks with files in its workspace. The workspace file's naming convention becomes a linked, evolving data structure:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

| Name Part   | Purpose                       | Changes                                        |
| ----------- | ----------------------------- | ---------------------------------------------- |
| `NNN`       | Sequence number (001, 002...) | Grows as work progresses                       |
| `task-slug` | Human-readable identifier     | Set at creation                                |
| `status`    | Current state                 | `active` → `complete`, `blocked`, or `handoff` |
| `_from-NNN` | Lineage suffix                | Links child tasks to parents                   |

Workspace files contain three sections that mirror `tether`'s development cycle:

| Section    | Purpose                                                                                      |
| ---------- | -------------------------------------------------------------------------------------------- |
| **Anchor** | The fixed point. Scope, exclusions, patterns, path, delta. Everything the model is bound to. |
| **Trace**  | Decision traces (T1, T2, T3...). Each must reference the Anchor. Verified between phases.    |
| **Close**  | What was delivered, what was *deliberately omitted*. Omitted must be non-empty.              |

## Workspaces as Persistent, Queryable Memory

With this structure, the filesystem becomes queryable memory. `ls workspace/` shows the active, ongoing work. `ls workspace/*_from-003*` reveals everything that emerged from task 003. Understanding compounds across sessions. When you come back tomorrow, the structure is waiting for you and ready to go.

## When to Use `tether`

`tether` is the right tool when:

- Precision matters more than speed
- Understanding must persist across sessions
- Reasoning needs to be visible and auditable
- Scope requires explicit negotiation with the model

## When Not to Use `tether`

For all of its power, `tether` does add overhead. While that overhead compounds into value over multi-session, complex work, it is the wrong tool for:

- Exploratory prototyping where you *want* the model to wander
- Autonomous long-running tasks (use Ralph or similar orchestrators)
- Simple one-off queries that need no persistence
