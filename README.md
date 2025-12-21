# Tether

Tether is a Claude Code plugin for disciplined, anchored, and tightly scoped development. It seizes the step function jump in Agentic coding capabilities unlocked by Opus 4.5. 

## Background 

Before Opus 4.5, most agent and tool orchestrations were implicitly working *around* the model's worst behaviors: scope creep and over-engineering. Coding assistants felt like overeager Junior-savants that needed careful steering whenever projects grew beyond clean and simple data flows. 

This pattern was cleanly broken by Opus 4.5. If you're reading this you've likely felt the shift. When talking to Opus 4.5, it *gets* it. The ineffable *it*. We can safely say this is the change in LLM Agents from spastic assistants to powerful, intelligent collaborators.


## Core Principle: The Workspace

Tether builds on this agentic paradigm shift with a Workspace. Workspaces are the linked, evolving record of a project's scope, decisions, and implementations. They are built from structured markdown files with a naming convention inspired by Herbert A. Simon's List of Lists. We created them in this spirit to represent knowledge and action in constrained environments. And, most importantly, they persist across sessions.

### Workspace File Structure

Each task becomes a workspace file. The naming convention *is* the data structure:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

| Name Part   | Purpose                       | Changes                                        |
| ----------- | ----------------------------- | ---------------------------------------------- |
| `NNN`       | Sequence number (001, 002...) | Grows as work progresses                       |
| `task-slug` | Human-readable identifier     | Set at creation                                |
| `status`    | Current state                 | `active` → `complete`, `blocked`, or `handoff` |
| `_from-NNN` | Lineage suffix                | Links child tasks to parents                   |

Workspace files have three sections that mirror tether's development cycle:

| Section    | Purpose                                                                                                             |
| ---------- | ------------------------------------------------------------------------------------------------------------------- |
| **Anchor** | The fixed point. Scope, exclusions, patterns to follow, path, and delta—everything you're bound to.                 |
| **Trace**  | The reasoning traced during build. Patterns noticed, decisions made, constraints hit—written *before* implementing. |
| **Close**  | The proof. What was delivered, what was deliberately omitted, why.                                                  |

### Workspaces as Persistent, Queryable Memory

With this structure, the filesystem becomes queryable memory. `ls workspace/` shows the active, ongoing work. `ls workspace/*_from-003*` reveals everything that emerged from task 003. Understanding compounds across sessions. When you return tomorrow, the structure is waiting and ready to go.

## Installation

Add the tether plugin to your marketplace and install it. 
```bash
claude /plugin install <your-marketplace>/tether
```

Make sure to update the marketplace.json file to include the plugin.


## Guiding Philosophy

Tether bases all of its work on the following key principles:

| Principle                  | Description                                             |
| -------------------------- | ------------------------------------------------------- |
| **Edit over create**       | Modify what exists before creating something new.       |
| **Concrete over abstract** | Build the specific solution, not an abstract framework. |
| **Present over future**    | Implement current requirements, not anticipated ones.   |
| **Explicit over clever**   | Choose clarity over sophistication.                     |


## tether's Development Cycle

Tether follows a four-phase development cycle in rhythm with its guiding principles:

1. **Assess** — Can this anchor to a single behavior? Does it need a workspace file, or is execution obvious?
2. **Anchor** — Create the workspace file. Define the scope boundary and path. Crucially, it writes what the model will *not* do.
3. **Build** — Implement. Traces reasoning before coding. If scope is creeping, tether stops and clarifies.
4. **Close** — Add specific omissions and rename the file with its final status.

These phases help scope creep and over-engineering become visible *before* they leak and compound.

## Architecture

Tether is a plugin made up of Claude skills, agents, and commands:

| Component               | Purpose                                                                    |
| ----------------------- | -------------------------------------------------------------------------- |
| **Skill**               | Auto-invoked on create/build/implement. Embeds the checkpoint methodology. |
| **code-builder agent**  | Test-first implementation. Edits over creates. No unprompted abstractions. |
| `/tether:workspace`     | Query active tasks and their lineage.                                      |
| `/tether:anchor [task]` | Create a new workspace file with scope boundary.                           |
| `/tether:close [task]`  | Complete a task. Add omissions. Rename to final status.                    |
| `/tether:drift`         | Review current work against its anchor for scope creep.                    |

## Command Usage

```bash
/tether:workspace                              # check existing work
/tether:anchor implement password reset flow   # start new task
/tether:close password-reset                   # complete task
```

## When to Use Tether

Tether is the right tool when:

- Precision matters more than speed
- Understanding must persist across sessions
- Reasoning needs to be visible and auditable
- Scope requires explicit negotiation with the model

## When Not to Use Tether

For all of its power, tether does add overhead. While that overhead compounds into value over multi-session, complex work, it is the wrong tool for:

- Exploratory prototyping where you *want* the model to wander
- Autonomous long-running tasks (use Ralph or similar orchestrators)
- Simple one-off queries that need no persistence

