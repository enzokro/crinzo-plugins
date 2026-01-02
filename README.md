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

---

## ctx

A companion plugin that transforms tether's workspace into a queryable context graph. Decisions become primary entities. Patterns become edges.

### The Gap ctx Closes

tether externalizes decision traces. Each completed file captures Path, Delta, Thinking Traces, and Delivered. But without tooling, this knowledge sits inert—grep works, but precedent retrieval requires reading files.

ctx indexes workspace files as decision records. It extracts structure (Path, Delta), captures reasoning (Thinking Traces), tracks patterns (`#pattern/`, `#constraint/`, `#decision/`), and derives relationships (lineage chains, file impact, pattern usage).

### Data Model

```
.ctx/
├── index.json    # Decision records with full context
├── edges.json    # Derived relationships
└── signals.json  # Outcome tracking (+/-)
```

Decisions are primary. Patterns are edges connecting them.

### Commands

| Command | Purpose |
|---------|---------|
| `/ctx <topic>` | Surface relevant decisions |
| `/ctx:decision NNN` | Full decision record with traces |
| `/ctx:lineage NNN` | Decision ancestry chain |
| `/ctx:trace <pattern>` | Find decisions using a pattern |
| `/ctx:impact <file>` | Find decisions affecting a file |
| `/ctx:age [days]` | Find stale decisions |
| `/ctx:signal +/- <pattern>` | Mark pattern outcome |
| `/ctx:mine` | Build decision index |

### Example

```bash
# Build the index
/ctx:mine
# Indexed 12 decisions, 8 patterns from workspace

# Query precedent
/ctx auth
# [015] auth-refactor (3d ago, complete)
#   Path: User credentials → validation → session token
#   Delta: src/auth/*.ts
#   Builds on: 008

# Trace a pattern's usage
/ctx:trace #pattern/session-token-flow
# Decisions using #pattern/session-token-flow:
#   [015] auth-refactor (3d, complete)
#   [023] session-timeout (1d, complete)

# Track outcomes
/ctx:signal + #pattern/session-token-flow
# Signal added: #pattern/session-token-flow -> net 2
```

### Graph Relationships

| Edge | Query |
|------|-------|
| `decision → parent` | `/ctx:lineage NNN` |
| `pattern → decisions` | `/ctx:trace #pattern/name` |
| `file → decisions` | `/ctx:impact src/auth` |

Lineage comes from `_from-NNN` suffixes. Pattern edges come from tags. File edges come from Delta parsing.

### Weighting

```
score = relevance * recency_factor * signal_factor
```

Recent, positively-signaled patterns rank highest. Stale decisions surface via `/ctx:age`.

### Integration with tether

ctx reads workspace files. It doesn't modify them. tether writes the decision traces; ctx makes them queryable.

The intended flow:
1. tether's Anchor phase could query ctx for relevant precedent
2. tether's Reflect phase produces the patterns ctx indexes
3. ctx surfaces what tether accumulated

For now, ctx operates parallel to tether. Integration hooks are future work.

---

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
