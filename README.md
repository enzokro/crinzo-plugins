# tether

A Claude Code plugin for focused, scope-controlled development. Prevents over-engineering and scope creep through Path and Delta anchoring.

## Background

Before Opus 4.5, agents spent most of their prompt budget working *around* the worst tendencies of LLMs: scope creep and over-engineering. Coding assistants behaved like overeager savants that had to be carefully steered whenever projects grew even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, you've likely felt the shift. Talking to Opus 4.5, it *gets* it. The ineffable *it*. We are now living the transformation of LLM agents from spastic assistants to powerful, intelligent collaborators.

`tether` leverages this shift. It combines the model's increased capabilities with structural discipline through two core constructs:

- **Path**: Data transformation (`Input → Processing → Output`). Not goals—transformations.
- **Delta**: Minimal change scope. What gets touched; what doesn't.

Both must exist before implementation. This is the gate.

## Philosophy

`tether` is built on four principles:

| Principle | Meaning |
|-----------|---------|
| **Present over future** | Implement current requests, not anticipated future needs |
| **Concrete over abstract** | Build a specific solution, not abstract frameworks |
| **Explicit over clever** | Always choose clarity over sophistication |
| **Edit over create** | Modify what exists before creating something new |

These aren't novel. They read as obvious 101s of software development. But anyone who's spent time building with LLMs knows: agents are ambitious and like to stay busy. They often deviate from these principles and tech debt accumulates, especially in complex projects. `tether` enforces these principles through Path and Delta as fixed points that gate the entire development process.

## Why This Matters

Enterprise software captures *what happened*. It doesn't capture *why decisions were made*—the exceptions, precedents, cross-system context that lives in Slack threads and people's heads.

`tether`'s workspace externalizes decision traces. Each task records what transformation was needed, what scope was bounded, what was discovered, and what was delivered. Over time, the workspace becomes a context graph—queryable memory of how problems were solved.

## Architecture

```
[Assess] → route → [Anchor] → Path+Delta → [Build] → complete → [Reflect]
```

| Agent | Purpose | Model |
|-------|---------|-------|
| `tether:assess` | Route: full / direct / clarify | haiku |
| `tether:anchor` | Establish Path, Delta, Thinking Traces | inherit |
| `tether:code-builder` | Implement within constraints | inherit |
| `tether:reflect` | Extract patterns (opt-in via `#reflect` tag) | inherit |

**Runtime enforcement**: The `hooks/delta-check.sh` hook blocks edits to files outside declared Delta scope.

## Workspace

Files live in `workspace/`. Naming is structural:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

- `NNN`: Sequence (001, 002...)
- `status`: active, complete, blocked
- `_from-NNN`: Lineage (builds on prior task)

### File Structure

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change]

## Thinking Traces
[exploration findings, decisions]

## Delivered
[what was implemented]
Commit: abc1234
```

### Querying

```bash
ls workspace/                                    # list all
ls workspace/*_from-003*.md                      # lineage from 003
grep -h "^#pattern/" workspace/*_complete*.md    # accumulated patterns

# WQL (optional)
python3 tether/wql/wql.py stat                   # status counts
python3 tether/wql/wql.py lineage 003            # trace ancestry
python3 tether/wql/wql.py graph                  # tree view
```

## Commands

| Command | Purpose |
|---------|---------|
| `/tether:tether` | Invoke orchestrator |
| `/tether:workspace` | Query workspace state |
| `/tether:anchor` | Create workspace file manually |
| `/tether:close` | Complete task manually |

## Installation

```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins.git
```

Then install `tether` from the marketplace.

## When to Use

Use `tether` when:
- Precision matters more than speed
- Understanding must persist across sessions
- Path needs to be explicit before implementation

Don't use for:
- Exploratory prototyping (where you *want* the model to wander)
- Simple one-off queries that need no persistence
- Quick fixes or mechanical changes
