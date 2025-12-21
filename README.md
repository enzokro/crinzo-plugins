# Tether

Tether is a Claude Code plugin for disciplined, anchored, and tightly scoped development. It seizes the step function jump in Agentic coding capabilities brought on by Opus 4.5. 

## Background 

Before Opus 4.5, most agent and tool orchestrations were implicitly working *around* models' worst patterns: scope creep and over-engineering. Coding assistants felt like overeager Junior-savants that we had to carefully steer whenever projects and tasks became more complex than clean, simple linear data flows. 

This pattern was cleanly broken by Opus 4.5. If you're reading this you've likely felt the profound shift. When talking to Opus 4.5, it *gets* it. The ineffable *it*. We can safely say we are now in the shift of LLM Agents from spastic assistants to powerful, intelligent collaborators.

## Core Principle: The Workspace

Tether builds on this agentic paradigm shift with a Workspace that represents knowledge and action in constrained environments. Workspaces are the linked, evolving record of a project's scope, decisions, and implementations. They are built from structured markdown files with a naming convention inspired by Herbert A. Simon's List of Lists.

Each task gets a file:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

The lineage suffix (`_from-NNN`) is how tasks reference their parents. Run `ls workspace/` to see all active work at a glance.

A workspace file contains three sections that mirror the development lifecycle:

| Section    | Purpose                                                                                       |
| ---------- | --------------------------------------------------------------------------------------------- |
| **Anchor** | The fixed point. Scope, exclusions, patterns to follow, path, and delta—everything you're bound to. |
| **Trace**  | The reasoning traced during build. Patterns noticed, decisions made, constraints hit—written *before* implementing. |
| **Close**  | The proof. What was delivered, what was deliberately omitted, why.                            |

## The Discipline

Tether follows a four-phase development rhythm:

1. **Assess** — Can this anchor to a single behavior? Does it need a workspace file, or is execution obvious?
2. **Anchor** — Create the workspace file. Define the scope boundary and path. Write what you will *not* do.
3. **Build** — Implement. Trace your reasoning before coding. If scope expands, stop.
4. **Close** — Add the omissions section. Rename the file to its final status.

These phases are how drift becomes visible *before* it leaks and compounds.

## Drift Signals

Certain phrases are reliable indicators of scope expansion.

- *"flexible," "extensible," "comprehensive"*
- *"while we're at it," "might as well"*
- *"in case," "future-proof"*

When tether detects these phrases, it halts and clarifies before moving.

## Components

Tether is a coordinated system of skills, agents, and commands:

| Component               | Purpose                                                                    |
| ----------------------- | -------------------------------------------------------------------------- |
| **Skill**               | Auto-invoked on create/build/implement. Embeds the checkpoint methodology. |
| **code-builder agent**  | Test-first implementation. Edits over creates. No unprompted abstractions. |
| `/tether:workspace`     | Query active tasks and their lineage.                                      |
| `/tether:anchor [task]` | Create a new workspace file with scope boundary.                           |
| `/tether:close [task]`  | Complete a task. Add omissions. Rename to final status.                    |
| `/tether:drift`         | Review current work against its anchor for scope creep.                    |

## Constraints

These are the load-bearing walls of tethered development:

| Constraint                 | Meaning                                                 |
| -------------------------- | ------------------------------------------------------- |
| **Edit over create**       | Modify what exists before creating something new.       |
| **Concrete over abstract** | Build the specific solution, not the general framework. |
| **Present over future**    | Implement current requirements, not anticipated ones.   |
| **Explicit over clever**   | Choose clarity over sophistication.                     |

## Omissions

Every completed task requires listing what was deliberately *not* implemented.

This is not bookkeeping. It is the forcing function that makes scope visible. "Nothing omitted" means you either scoped too narrowly or exceeded scope. Adjacent work always exists—name what you chose not to do.

## When to Use Tether

Tether is the right tool when:

- Precision matters more than speed
- Understanding must persist across sessions
- Reasoning needs to be visible and auditable
- Scope requires explicit negotiation with the model

## When Not to Use Tether

Tether adds overhead. That overhead compounds into value over multi-session, complex work. It is the wrong tool for:

- Exploratory prototyping where you *want* the model to wander
- Autonomous long-running tasks (use Ralph or similar orchestrators)
- Simple one-off queries that need no persistence

## Installation

Add this plugin to your marketplace and install it. 
```bash
claude /plugin install <your-marketplace>/tether
```

Make sure to update the marketplace.json file to include the plugin.

## Command Usage

```bash
/tether:workspace                              # check existing work
/tether:anchor implement password reset flow   # start new task
/tether:close password-reset                   # complete task
```

## Structure

```
tether/
├── skills/tether/
│   ├── SKILL.md
│   └── references/
├── agents/code-builder.md
└── commands/
```