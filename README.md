# tether

Agent orchestrator for focused development. Prevents scope creep and over-engineering through Path and Delta anchoring.

## Core Insight

LLM agents drift. They over-engineer, anticipate future needs, build abstractions. Tether counters this with two constructs:

- **Path**: Data transformation (`Input → Processing → Output`). Not goals; transformations.
- **Delta**: Minimal change scope. What gets touched; what doesn't.

Both must exist before implementation. This is the gate.

## Why This Matters

Enterprise software captures *what happened*. It doesn't capture *why decisions were made*—the exceptions, precedents, cross-system context that lives in Slack threads and people's heads.

Tether's workspace externalizes decision traces. Each task records:
- What transformation was needed (Path)
- What scope was bounded (Delta)
- What was discovered (Thinking Traces)
- What was delivered (Delivered)

Over time, the workspace becomes a context graph—queryable memory of how problems were solved.

## Principles

| Principle | Meaning |
|-----------|---------|
| Present over future | Current request, not anticipated needs |
| Concrete over abstract | Specific solution, not framework |
| Explicit over clever | Clarity over sophistication |
| Edit over create | Modify existing before creating new |

## Architecture

```
[Assess] → route → [Anchor] → Path+Delta → [Build] → complete → [Reflect]
```

| Agent | Purpose | Model |
|-------|---------|-------|
| `tether:assess` | Route: full / direct / clarify | haiku |
| `tether:anchor` | Establish Path, Delta, Thinking Traces | inherit |
| `tether:code-builder` | Implement within constraints | inherit |
| `tether:reflect` | Extract patterns (conditional) | inherit |

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
| `/tether:creep` | Check for scope drift |

## Installation

```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins.git
```

Then install `tether` from the marketplace.

## When to Use

Use when: precision matters, understanding should persist, path needs discovery.

Don't use for: exploratory prototyping, simple one-off queries, when you want the model to wander.
