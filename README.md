# tether

A Claude Code orchestrator for clean, focused development.

## Introduction

Before Opus 4.5, agentic tools and harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding assistants felt like overeager Junior-savants that had to be carefully managed whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`tether` is built on this shift. It combines the model's breakthrough capabilities and its improved understanding of our requests into a powerful, focused development workflow. It achieves this with two key concepts: `Path` and `Delta`.

- **Path**: The core data flow touched by a request.
- **Delta**: The minimal, targeted changes that fulfil that request.

However, context can still disappear. Agents can build up a full understanding of the codebase but, after a session ends, we're forced to start from scratch.

`tether` provides that missing memory. The orchestrator externalizes its thinking into a workspace. Tasks produce files with the Path, Delta, and exploration that led there. Over time, `tether` turns these files into a living store of decisions and knowledge. Understanding persists because it's actively transformed into a structured graph. This allows `tether` to grow with its projects by tracing the lineage of solutions to find emerging patterns. 

## Architecture

`tether` orchestrates a four stage development process:

```
[Assess] → route → [Anchor] → Path+Delta → [Build] → complete → [Reflect]
```

| Agent                 | Purpose                                      | Model   |
| --------------------- | -------------------------------------------- | ------- |
| `tether:assess`       | Route: full / direct / clarify               | haiku   |
| `tether:anchor`       | Establish Path, Delta, Thinking Traces       | inherit |
| `tether:code-builder` | Implement within constraints                 | inherit |
| `tether:reflect`      | Extract patterns (opt-in via `#reflect` tag) | inherit |


## Installation

Add this repo as a marketplace from inside Claude Code:

```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins.git
```

Then install `tether` from the marketplace.


## Philosophy

`tether` is built on four principles:

| Principle                  | Meaning                                                  |
| -------------------------- | -------------------------------------------------------- |
| **Present over future**    | Implement current requests, not anticipated future needs |
| **Concrete over abstract** | Build a specific solution, not abstract frameworks       |
| **Explicit over clever**   | Always choose clarity over sophistication                |
| **Edit over create**       | Modify what exists before creating something new         |

None of these are new. In fact, they read like the 101s of software development. But anyone who's spent time building with LLMs knows that agents are ambitious and like to stay busy. They often stray from these principles and quickly accumulate tech debt, especially in complex projects. `tether` anchors on `Path` and `Delta` to turn these principles into its north star.

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

| Command             | Purpose                        |
| ------------------- | ------------------------------ |
| `/tether:tether`    | Invoke orchestrator            |
| `/tether:workspace` | Query workspace state          |
| `/tether:anchor`    | Create workspace file manually |
| `/tether:close`     | Complete task manually         |

---

## lattice

Over time, `tether` workspaces accumulate decision traces. Each completed task captures Path, Delta, Thinking Traces, and Delivered. This is valuable context, but without tooling it sits inert. You can grep for patterns, but actually *retrieving* relevant precedent means reading through files manually.

`lattice` turns your workspace into a queryable context graph. It indexes decision records, extracts their structure, tracks the patterns you've tagged (`#pattern/`, `#constraint/`, `#decision/`), and derives relationships between them. When you're starting new work, you can ask lattice what you've done before that's relevant.

### Data Model

```
.lattice/
├── index.json    # Decision records with full context
├── edges.json    # Derived relationships (lineage, patterns, files)
└── signals.json  # Outcome tracking (+/-)
```

The graph treats decisions as nodes and patterns as edges connecting them. Lineage chains (from `_from-NNN` suffixes), pattern usage (from tags), and file impact (from Delta parsing) all become queryable relationships.

### Commands

| Command                         | Purpose                          |
| ------------------------------- | -------------------------------- |
| `/lattice <topic>`              | Surface relevant decisions       |
| `/lattice:decision NNN`         | Full decision record with traces |
| `/lattice:lineage NNN`          | Decision ancestry chain          |
| `/lattice:trace <pattern>`      | Find decisions using a pattern   |
| `/lattice:impact <file>`        | Find decisions affecting a file  |
| `/lattice:age [days]`           | Find stale decisions             |
| `/lattice:signal +/- <pattern>` | Mark pattern outcome             |
| `/lattice:mine`                 | Build decision index             |

### Example

```bash
# Build the index
/lattice:mine
# Indexed 12 decisions, 8 patterns from workspace

# Query precedent
/lattice auth
# [015] auth-refactor (3d ago, complete)
#   Path: User credentials → validation → session token
#   Delta: src/auth/*.ts
#   Builds on: 008

# Trace a pattern's usage
/lattice:trace #pattern/session-token-flow
# Decisions using #pattern/session-token-flow:
#   [015] auth-refactor (3d, complete)
#   [023] session-timeout (1d, complete)

# Track outcomes
/lattice:signal + #pattern/session-token-flow
# Signal added: #pattern/session-token-flow -> net 2
```

### Weighting

Results are ranked by recency and signal history. Recent work surfaces first, and patterns you've marked as successful (`/lattice:signal +`) get weighted higher. Patterns that caused problems (`/lattice:signal -`) fade from view. Over time, the graph learns which approaches work in your codebase.

### Integration with tether

`lattice` reads workspace files but never modifies them. `tether` writes the decision traces; `lattice` makes them searchable. The two plugins operate in parallel for now, though the natural integration point is obvious: Anchor could query for relevant precedent before planning, and Reflect could surface which patterns are emerging.

---

## When to Use

`tether` shines when precision matters more than speed, when understanding needs to persist across sessions, and when you want Path explicit before implementation begins. It's the right choice for complex features, architectural changes, and work that will be built upon later.

It's overkill for exploratory prototyping (where you *want* the model to wander), simple one-off queries, and quick mechanical fixes. Know when to reach for it.
