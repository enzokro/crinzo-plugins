# ftl

Knowledge compounds. Understanding persists.

## Introduction

Before Opus 4.5, agentic harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`ftl` is built on this shift. Where the old paradigm constrained models to prevent drift, `ftl` amplifies collaboration—persisting knowledge across sessions so we build on what we've already done instead of starting from an empty context window every time.

The north star: **augmentation, not replacement**. Human provides direction and judgment. AI provides capability and execution. Understanding compounds.

## Philosophy

| Principle | Meaning |
|-----------|---------|
| **Memory compounds** | Each task leaves the system smarter |
| **Verify first** | Shape work by starting with proof-of-success |
| **Bounded scope** | Workspace files are explicit so humans can audit agent boundaries |
| **Present over future** | Implement current requests, not anticipated needs |
| **Edit over create** | Modify what exists before creating something new |

These read like the 101s of good software development. Anyone who's worked with coding agents knows the models like to work and stay busy. Every part of `ftl` is built around these principles to turn them into its north star.

## Quick Start

```bash
# Add crinzo-plugins marketplace
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install ftl
claude plugin install ftl@crinzo-plugins
```

Or from within Claude Code:
```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install ftl@crinzo-plugins
```

## How It Works

```
/ftl <task> → router → builder → learner → workspace/
      ↓                                         ↓
/ftl campaign → planner → tasks → synthesizer → memory
      ↓                                         ↓
      └─────────── queries precedent ───────────┘
```

**Tasks** produce workspace files capturing decisions, reasoning, and patterns. **Memory** indexes these into a queryable knowledge graph. **Campaigns** coordinate multi-task objectives, querying memory for precedent before planning.

Each completed task makes the system smarter. Patterns emerge, get signaled, influence future work.

## Agents

| Agent | Role |
|-------|------|
| **Router** | Route + explore + anchor. Creates workspace for full tasks. |
| **Builder** | TDD implementation within Delta. Test-first, edit-over-create. |
| **Reflector** | Failure diagnosis. Returns RETRY with strategy or ESCALATE to human. |
| **Learner** | Extract patterns to Key Findings + index to memory. |
| **Planner** | Verification-first campaign decomposition. |
| **Synthesizer** | Cross-campaign meta-pattern extraction. |

## Commands

### Core

| Command | Purpose |
|---------|---------|
| `/ftl:ftl <task>` | Execute task (routes to direct or full) |
| `/ftl:ftl campaign <objective>` | Plan and execute multi-task campaign |
| `/ftl:ftl query <topic>` | Surface relevant precedent from memory |
| `/ftl:ftl status` | Combined campaign + workspace status |

### Workspace

| Command | Purpose |
|---------|---------|
| `/ftl:workspace` | Query state, lineage, tags |
| `/ftl:close` | Complete active task manually |

### Memory

| Command | Purpose |
|---------|---------|
| `/ftl:learn` | Force pattern synthesis |
| `/ftl:signal +/- #pattern` | Mark pattern outcome (+/-) |
| `/ftl:trace #pattern` | Find decisions using a pattern |
| `/ftl:impact <file>` | Find decisions affecting a file |
| `/ftl:age [days]` | Find stale decisions |
| `/ftl:decision NNN` | Full decision record with traces |

## Workspace Format

Tasks routed to `full` produce workspace files in `workspace/`:

```markdown
# NNN: [Decision Title]

## Question
[What decision does this resolve?]

## Precedent
[Injected from memory — patterns, antipatterns, related decisions]

## Options Considered
[Alternatives explored and rejected]

## Decision
[Explicit choice with rationale]

## Implementation
Path: [Input] → [Processing] → [Output]
Delta: [files in scope]
Verify: [test command]

## Thinking Traces
[Exploration, dead ends, discoveries]

## Delivered
[What was implemented]

## Key Findings
#pattern/name #constraint/name
```

Naming: `NNN_task-slug_status[_from-NNN].md`
- Status: `active`, `complete`, `blocked`
- `_from-NNN` indicates lineage (builds on prior task)

## Memory

Single source of truth: `.ftl/memory.json`

Stores decisions, patterns, signals, and lineage. Query with `/ftl:ftl query <topic>`. Mark outcomes with `/ftl:signal + #pattern/name`.

Patterns with positive signals surface higher in future queries. Patterns with negative signals fade. The graph learns which approaches work in your codebase.

## Examples

```bash
# Simple task — routes to direct, no workspace
/ftl:ftl fix typo in README

# Complex task — routes to full, creates workspace
/ftl:ftl add user authentication

# Multi-task campaign
/ftl:ftl campaign implement OAuth with Google and GitHub

# Query what you've done before
/ftl:ftl query session handling

# Check status
/ftl:ftl status

# Mark a pattern as successful
/ftl:signal + #pattern/session-token-flow

# Find what touched a file
/ftl:impact src/auth/
```

## When to Use

**Use ftl when:**
- Work should persist as precedent
- You want bounded, reviewable scope
- Knowledge should compound across sessions
- Multi-task objectives need coordination

**Skip ftl when:**
- Exploratory prototyping—let the model wander
- Quick one-offs with no future value
- Simple queries you'd ask Claude directly

Know when to reach for these tools.
