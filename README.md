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
/ftl <task> → router → builder → learner → memory.json

CAMPAIGN MODE:
/ftl campaign <obj> → planner → [builder]* → synthesizer → memory.json
                          ↑                                      ↓
                          └────────── queries precedent ─────────┘
```

**Tasks** produce workspace files capturing decisions, reasoning, and patterns. **Memory** indexes these into queryable knowledge. **Campaigns** coordinate multi-task objectives with adaptive learning — the synthesizer runs only when there's something new to learn.

Each completed task makes the system smarter. Patterns emerge over time to influence future work.

## Agents

Six agents with distinct roles and model assignments:

| Agent | Model | Role |
|-------|-------|------|
| **Router** | Sonnet | Classify tasks, create workspaces, inject memory (TASK mode) |
| **Builder** | Opus | Transform workspace spec into code (SPEC/BUILD tasks) |
| **Builder-Verify** | Sonnet | Execute VERIFY tasks and simple DIRECT changes |
| **Planner** | Opus | Decompose objectives into verifiable tasks (CAMPAIGN mode) |
| **Learner** | Opus | Extract patterns from single workspace (TASK mode) |
| **Synthesizer** | Opus | Extract failures/discoveries from campaign workspaces |

**Constraints:**
- Learner and Synthesizer are mutually exclusive — Learner handles single tasks, Synthesizer handles campaigns
- Tool budgets enforce focus: Builder gets 5 tools (FULL) or 3 (DIRECT), Builder-Verify gets 3
- Synthesizer is conditionally gated — runs only when blocked workspaces exist or new frameworks are encountered

## Execution Modes

**FULL mode** (default for SPEC/BUILD):
- 5-tool budget with retry-once on known failure match
- Workspace file with code context and framework idioms
- Quality checkpoint before completion

**DIRECT mode** (simple changes, final VERIFY):
- 3-tool budget, no retry
- No workspace file — inline execution
- Sonnet model via Builder-Verify agent

## Commands

### Core

| Command                         | Purpose                                 |
| ------------------------------- | --------------------------------------- |
| `/ftl:ftl <task>`               | Execute task (routes to DIRECT or FULL) |
| `/ftl:ftl campaign <objective>` | Plan and execute multi-task campaign    |
| `/ftl:ftl query <topic>`        | Surface relevant precedent from memory  |
| `/ftl:ftl status`               | Combined campaign + workspace status    |

### Workspace

| Command          | Purpose                       |
| ---------------- | ----------------------------- |
| `/ftl:workspace` | Query state, lineage, graph   |
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

Tasks produce XML workspace files in `.ftl/workspace/`. Each workspace is a contract between planner and builder — what to do, how to verify, and what to watch out for.

```xml
<workspace id="003-routes-crud" type="BUILD" mode="FULL" status="active">
  <implementation>
    <delta>src/routes.py</delta>
    <verify>pytest routes/test_*.py -v</verify>
    <framework>FastHTML</framework>
  </implementation>
  <code_context>
    <file path="src/routes.py" lines="1-60">
      <content language="python">...</content>
      <exports>create_route, handle_request</exports>
    </file>
    <lineage>
      <parent>002-database</parent>
      <prior_delivery>Created database schema</prior_delivery>
    </lineage>
  </code_context>
  <framework_idioms framework="FastHTML">
    <required><idiom>use @rt decorator for routes</idiom></required>
    <forbidden><idiom>raw HTML string construction</idiom></forbidden>
  </framework_idioms>
  <prior_knowledge>
    <pattern name="stubs-in-first-build" saved="2293760000">...</pattern>
    <failure name="import-order" cost="2500">...</failure>
  </prior_knowledge>
  <preflight>
    <check>python -m py_compile src/routes.py</check>
  </preflight>
  <delivered status="pending">...</delivered>
</workspace>
```

**Naming:** `NNN_task-slug_status.xml`
- `NNN` — 3-digit sequence (000, 001, 002)
- `status` — `active`, `complete`, or `blocked`

The workspace is the builder's single source of truth. Framework idioms are non-negotiable. If something goes wrong that isn't in prior knowledge, the builder blocks — discovery is needed, not more debugging.

## Memory

A unified system capturing what went wrong and what was decided:

| File                 | Purpose                                           |
| -------------------- | ------------------------------------------------- |
| `.ftl/memory.json`   | Failures, discoveries, decisions, edges           |

**Failures** — Observable errors with executable fixes. Each failure includes: a trigger (the error message), a fix (the action that resolves it), a match regex (to catch in logs), and a prevent command (pre-flight check). This is where "don't repeat mistakes" lives.

**Discoveries** — Non-obvious insights that save significant tokens. High bar: a senior dev would be surprised by this. If it's obvious, it doesn't belong here.

**Decisions** — Choices made with rationale. Each decision tracks options considered, the choice made, files touched, and thinking traces. This is precedent for future tasks.

### Signal Evolution

Patterns with positive signals (`/ftl:signal +`) surface higher in future queries. Patterns with negative signals fade. Net +5 gets 2x weight. Net -5 gets hidden. The system learns which approaches work in *your* codebase over time.

## Examples

```bash
# Simple task — routes to DIRECT, no workspace
/ftl:ftl fix typo in README

# Complex task — routes to FULL, creates workspace
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
