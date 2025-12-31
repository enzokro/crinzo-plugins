# `tether`

`tether` is a Claude Code agent orchestrator for clean and focused development. It builds on the step function jump in agentic coding capabilities unlocked by Opus 4.5.

## Background

Before Opus 4.5, Agents dedicated most of their prompts and tools to working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding assistants behaved like overeager Junior-savants that had to be carefully steered whenever projects grew even moderately complex.

Opus 4.5 broke this pattern. If you're reading this then you've likely felt the shift. Talking to Opus 4.5, it *gets* it. The ineffable *it*. We are now living the transformation of LLM Agents from spastic assistants to powerful, intelligent collaborators.

`tether` combines the model's increased capabilities *and* their better understanding of our needs into a powerful development harness. Path and Delta anchor all work. The workspace persists understanding across sessions. And all of this fully leverages Opus 4.5's capabilities.

# Philosophy

`tether` is based on four principles to keep Agents focused on the task at hand:

| Principle                  | Description                                               |
| -------------------------- | --------------------------------------------------------- |
| **Present over future**    | Implement current requests, not anticipated future needs. |
| **Concrete over abstract** | Build a specific solution, not abstract frameworks.       |
| **Explicit over clever**   | Always choose clarity over sophistication.                |
| **Edit over create**       | Modify what exists before creating something new.         |

`tether` turns these principles into its north star through two core constructs: **Path** (the data transformation) and **Delta** (the minimal change).

# Installation

Add the tether plugin to your marketplace and install it.
```bash
claude /plugin install <your-marketplace>/tether
```

Make sure to update the marketplace.json file to include the plugin.
> TODO: add plugin to marketplace proper


# Architecture

`tether` follows a development cycle with three phases. Each phase is delegated to an agent with bounded context. For complex tasks, the orchestrator chronicles its process in a workspace file.

```
[Assess] → route → [Anchor] → Path+Delta → [Build] → complete
    ↓                  ↓                        ↓
 decide              gate                   implement
```

**The single gate:** Path and Delta must exist before Build proceeds.

## Tether Agents

| Agent                        | Purpose                                  | Model   |
| ---------------------------- | ---------------------------------------- | ------- |
| `tether:tether-orchestrator` | Coordinates phases                       | inherit |
| `tether:assess`              | Routing decision                         | haiku   |
| `tether:anchor`              | Creates workspace, establishes Path/Delta | inherit |
| `tether:code-builder`        | Implementation + completion              | inherit |

## Phase 1: Assess

The `assess` Agent decides whether we are dealing with a simple ask that can be done ad hoc or a complex task that requires more deliberation.

| Actionable? | Needs thinking? | Route to           |
| ----------- | --------------- | ------------------ |
| Yes         | Yes             | Anchor (full flow) |
| Yes         | No              | Build (direct)     |
| No          | —               | User (clarify)     |

## Phase 2: Anchor

The `anchor` Agent explores the codebase, establishes Path and Delta, and fills Thinking Traces with exploration findings.

**Path** — the data transformation:
```
Path: User request → API endpoint → Database update → Response
```

**Delta** — the minimal change:
```
Delta: Add single endpoint, modify one handler, no new abstractions
```

**Thinking Traces** — exploration findings:
```
## Thinking Traces
- Auth pattern uses JWT in `src/auth/token.ts:45`
- Similar feature exists in `src/features/export.ts` - follow that structure
- Will need to modify `src/api/routes.ts` to add endpoint
```

## Phase 3: Build

The `build` Agent implements what the Anchor defines, nothing more and nothing less. When complete, it fills the Delivered section and renames the workspace file to `_complete`.

The workspace file serves as cognitive surface. Thinking Traces captures exploration and implementation thinking.

## Tether Commands

| Command                 | Purpose                              |
| ----------------------- | ------------------------------------ |
| `/tether:workspace`     | Query active tasks and their lineage |
| `/tether:anchor [task]` | Manually create a workspace file     |
| `/tether:close [task]`  | Manually complete a task             |
| `/tether:creep`         | Check for scope creep during Build   |


# The Workspace: Externalized Knowledge Across Sessions

`tether` builds on this agentic paradigm shift with a Workspace. Workspaces are the linked, evolving record of a project's understanding and implementations. They persist across sessions.

## Workspace File Structure

```
workspace/NNN_task-slug_status[_from-NNN].md
```

| Name Part   | Purpose                       | Changes                              |
| ----------- | ----------------------------- | ------------------------------------ |
| `NNN`       | Sequence number (001, 002...) | Grows as work progresses             |
| `task-slug` | Human-readable identifier     | Set at creation                      |
| `status`    | Current state                 | `active` → `complete` or `blocked`   |
| `_from-NNN` | Lineage suffix                | Links child tasks to parents         |

### File Contents

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Thinking Traces
[exploration findings, decisions, pen and paper during build]

## Delivered
[filled at completion]
```

| Section      | Purpose                                      |
| ------------ | -------------------------------------------- |
| **Anchor**   | Path and Delta. The fixed point.             |
| **Thinking Traces** | Externalized thinking. Exploration findings, decisions, pen and paper. Becomes crystallized knowledge. |
| **Delivered**| What was implemented. Filled at completion.  |

## Workspaces as Persistent, Queryable Memory

With this structure, the filesystem becomes queryable memory. `ls workspace/` shows the active, ongoing work. `ls workspace/*_from-003*` reveals everything that emerged from task 003. Understanding compounds across sessions.

## When to Use `tether`

`tether` is the right tool when:

- Precision matters more than speed
- Understanding must persist across sessions
- Path needs to be explicit before implementation

## When Not to Use `tether`

`tether` does add overhead. It is the wrong tool for:

- Exploratory prototyping where you *want* the model to wander
- Autonomous long-running tasks
- Simple one-off queries that need no persistence
