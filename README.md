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

The system has nine agents. Five handle the core work of routing, building, and learning. Four evaluate what happened so the system can get smarter.

### Core Agents

| Agent           | Role                                                                 |
| --------------- | -------------------------------------------------------------------- |
| **Router**      | Classify tasks, create workspaces, inject memory patterns            |
| **Builder**     | Transform workspace spec into code (5-tool max, TDD)                 |
| **Planner**     | Decompose objectives into verifiable tasks (campaigns only)          |
| **Learner**     | Extract patterns from single workspace (TASK mode)                   |
| **Synthesizer** | Extract failures/discoveries from all workspaces (CAMPAIGN mode)     |

### Evaluation Agents

| Agent              | Role                                                              | Registered |
| ------------------ | ----------------------------------------------------------------- | ---------- |
| **Observer**       | Compute information theory metrics (epiplexity, entropy, IGR)     | Yes        |
| **Meta-Reflector** | Analyze completed runs, maintain reflection journal               | Yes        |
| **Save Evaluator** | Evaluate quality of extracted patterns and failures               | Harness    |
| **Load Evaluator** | Evaluate memory injection efficacy and utilization                | Harness    |

*Registered agents can be spawned via Task tool. Harness agents are prompt definitions used by the external evaluation framework.*

**Constraint:** Learner and Synthesizer are mutually exclusive — using Learner in campaign mode is a category error.

**Tool Budgets:** Builder has a hard 5-tool limit. Router gets 2 reads, 1 bash, 1 write. Synthesizer gets 10. These constraints exist because if the agent hasn't solved it within budget, it's exploring, not debugging.

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

Tasks produce workspace files in `.ftl/workspace/`. Each workspace is a contract between the planner and builder — what to do, how to verify, and what to watch out for.

```markdown
# NNN: task-slug

## Implementation
Delta: files to modify
Verify: `command that proves success`

## Patterns
- **pattern-name** (saved: Xk tokens)
  When: condition that triggers this pattern
  Insight: what to do differently

## Known Failures
- **failure-name** (cost: Xk tokens)
  Trigger: observable error or regex
  Fix: specific action to resolve

## Pre-flight
- [ ] `python -m py_compile file.py`
- [ ] `pytest --collect-only -q`

## Implementation Requirements
[Detailed specs, code snippets, constraints]

## Escalation
After 2 failures OR 5 tools: BLOCK
"Discovery needed: [describe unknown issue]"
This is SUCCESS (informed handoff), not failure.

## Delivered
[What was actually implemented]
```

**Naming:** `NNN_task-slug_status.md`
- `NNN` — 3-digit sequence (000, 001, 002)
- `status` — `active`, `complete`, or `blocked`

The workspace is the builder's only source of truth. Patterns and Known Failures are injected from memory. Pre-flight checks run before Verify. If something goes wrong that isn't in Known Failures, the builder blocks — discovery is needed, not more debugging.

## Memory

Two complementary systems. One captures what went wrong (and how to fix it). The other captures what was decided (and why).

| File                 | Purpose                                           | Updated By   |
| -------------------- | ------------------------------------------------- | ------------ |
| `.ftl/memory.json`   | Failures with fixes, discoveries with evidence    | Synthesizer  |
| `.ftl/graph.json`    | Decisions, patterns, lineage, experiences         | Learner      |

### What Each System Stores

**Failures** (memory.json) — Observable errors with executable fixes. Each failure includes: a trigger (the error message), a fix (the action that resolves it), a match regex (to catch in logs), and a prevent command (pre-flight check). This is where "don't repeat mistakes" lives.

**Discoveries** (memory.json) — Non-obvious insights that save significant tokens. High bar: a senior dev would be surprised by this. If it's obvious, it doesn't belong here.

**Decisions** (graph.json) — Choices made with rationale. Each decision tracks options considered, the choice made, files touched, and thinking traces. This is precedent for future tasks.

**Experiences** (graph.json) — Failure modes with symptoms, diagnosis, prevention, and recovery actions. More structured than raw failures, with escalation triggers built in.

### Signal Evolution

Patterns with positive signals (`/ftl:signal +`) surface higher in future queries. Patterns with negative signals fade. Net +5 gets 2x weight. Net -5 gets hidden. The system learns which approaches work in *your* codebase over time.

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
