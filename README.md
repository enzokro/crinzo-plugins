# ftl

A Claude Code orchestrator that builds knowledge over time.

## Introduction

Before Opus 4.5, agentic harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding agents felt like overeager junior-savants that had to be carefully steered whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`ftl` is built on this shift. While previous harnesses constrained models to prevent drift, `ftl` persists knowledge across sessions to build on what we've already done instead of always starting from an empty context window.


## Philosophy

| Principle               | Meaning                                                           |
| ----------------------- | ----------------------------------------------------------------- |
| **Memory compounds**    | Each task leaves the system smarter                               |
| **Verify first**        | Shape work by starting with proof-of-success                      |
| **Bounded scope**       | Workspace files are explicit so humans can audit agent boundaries |
| **Present over future** | Implement current requests, not anticipated needs                 |
| **Edit over create**    | Modify what exists before creating something new                  |

These aren't new. In fact, they read like the 101s of good software development. But anyone who's worked with coding agents knows that the models like to work and stay busy. Every part of `ftl` is built around these principles to turn them into the orchestrator's north star.

## Quick Start

```bash
# Add the crinzo-plugins marketplace
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install ftl
claude plugin install ftl@crinzo-plugins
```

Or from inside of Claude Code:
```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install ftl@crinzo-plugins
```

## Development Loop

```
TASK MODE:
/ftl <task> → router → builder → learner → graph.json

CAMPAIGN MODE:
/ftl campaign <obj> → planner → [router → builder]* → synthesizer → memory.json
                                      ↑                                  ↓
                                      └────── queries precedent ─────────┘
```

**Tasks** produce workspace files capturing decisions, reasoning, and patterns. **Memory** indexes these into a queryable knowledge graph. **Campaigns** coordinate multi-task objectives, querying memory for precedent before planning.

Each completed task makes the system smarter. Patterns emerge over time to influence future work.

## Agents

| Agent           | Role                                                                 |
| --------------- | -------------------------------------------------------------------- |
| **Router**      | Classify tasks, create workspaces, inject memory patterns.           |
| **Builder**     | Transform workspace spec into code. 5-tool budget, TDD.              |
| **Planner**     | Decompose objectives into verifiable tasks (campaigns only).         |
| **Learner**     | Extract patterns from single workspace (TASK mode).                  |
| **Synthesizer** | Extract failures/discoveries from all workspaces (CAMPAIGN mode).    |

**Note:** Learner and Synthesizer are mutually exclusive — Learner runs in TASK mode, Synthesizer runs in CAMPAIGN mode.

## Commands

### Core

| Command                         | Purpose                                 |
| ------------------------------- | --------------------------------------- |
| `/ftl:ftl <task>`               | Execute task (routes to direct or full) |
| `/ftl:ftl campaign <objective>` | Plan and execute multi-task campaign    |
| `/ftl:ftl query <topic>`        | Surface relevant precedent from memory  |
| `/ftl:ftl status`               | Combined campaign + workspace status    |

### Workspace

| Command          | Purpose                       |
| ---------------- | ----------------------------- |
| `/ftl:workspace` | Query state, lineage, tags    |
| `/ftl:close`     | Complete active task manually |

### Memory

| Command                    | Purpose                          |
| -------------------------- | -------------------------------- |
| `/ftl:learn`               | Force pattern synthesis          |
| `/ftl:signal +/- #pattern` | Mark pattern outcome (+/-)       |
| `/ftl:trace #pattern`      | Find decisions using a pattern   |
| `/ftl:impact <file>`       | Find decisions affecting a file  |
| `/ftl:age [days]`          | Find stale decisions             |
| `/ftl:decision NNN`        | Full decision record with traces |

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

Two complementary memory systems:

| File | Purpose | Updated By |
|------|---------|------------|
| `.ftl/memory.json` | Failures and discoveries (cross-campaign learning) | Synthesizer |
| `.ftl/graph.json` | Decisions, patterns, lineage (decision graph) | Learner |

**Failures** capture what went wrong and how to fix it — observable errors with executable fixes. **Discoveries** capture non-obvious insights that save significant tokens. **Decisions** track choices made with rationale, building precedent for future tasks.

Patterns with positive signals surface higher in future queries. Patterns with negative signals fade. The system learns which approaches work in your codebase.

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
- Work should persist as precedent and compound over time
- You want bounded, reviewable scope
- Knowledge should build and evolve over sessions
- Complex objectives that need coordination

**Skip ftl when:**
- Exploratory prototyping where you want the models to wander
- Quick one-offs with no future value
- Simple queries you'd ask Claude directly
