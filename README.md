# tether

A Claude Code orchestrator for clean, focused development.

## Introduction

Before Opus 4.5, agentic tools and harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding assistants felt like overeager Junior-savants that had to be carefully managed whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`tether` is built on this shift. It combines the model's breakthrough capabilities and its improved understanding of our requests into a powerful, focused development workflow. It achieves this with two key concepts: `Path` and `Delta`.

- **Path**: The core data flow touched by a request.
- **Delta**: The minimal, targeted changes that fulfil that request.

However, context can still disappear. Agents can build up a full understanding of the codebase but, after a session ends, we're forced to start from scratch.

`tether` provides that missing memory with its sister plugin: `lattice`. The main orchestrator externalizes its thinking into a workspace. Tasks produce files with the Path, Delta, and exploration that led there. Over time, `lattice` turns these files into a living store of decisions and knowledge. Understanding persists because it's actively being transformed and structured. This allows `tether` to grow with its projects by tracing the lineage of solutions to find emerging patterns. 

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

### Option 1: Direct from GitHub (Recommended)

Install crinzo-plugins directly without cloning:

```bash
# Add crinzo-plugins marketplace from GitHub
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install tether (core orchestrator - recommended starting point)
claude plugin install tether

# Install lattice (semantic memory for workspaces)
claude plugin install lattice

# Install forge (meta-orchestrator for campaigns)
claude plugin install forge
```

### Option 2: From within Claude Code

```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install tether
/plugin install lattice
/plugin install forge
```

### What's Included

| Plugin | Description |
|--------|-------------|
| **tether** | Core orchestrator with 5 agents (tether-orchestrator, assess, anchor, code-builder, reflect), 4 commands, and output style. Prevents scope creep via Path+Delta anchoring. |
| **lattice** | Semantic memory with 2 agents (miner, surface), 7 commands, session hooks, and output style. Makes workspace decisions queryable. |
| **forge** | Meta-orchestrator with 5 agents (forge-orchestrator, planner, reflector, synthesizer, scout), 4 commands, and output style. Coordinates multi-task campaigns. |

### Recommended Setup

For most users, start with just `tether`:

```bash
/plugin install tether
```

Add `lattice` when your workspace accumulates enough decisions to benefit from semantic search:

```bash
/plugin install lattice
```

Add `forge` when you're working on multi-task objectives that span sessions:

```bash
/plugin install forge
```


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

## forge

`forge` is the meta-orchestrator that binds `tether` and `lattice` together. Where Ralph Wiggum is a dumb re-injection loop, `forge` compounds knowledge across sessions.

### Core Concept: Campaign

Not project (too permanent). Not task (too granular). A **campaign** is a bounded objective spanning multiple tether tasks:
- "Add OAuth with Google and GitHub"
- "Refactor auth module"
- "Implement real-time notifications"

Each campaign has clear success criteria and decomposes into sequenced tether tasks.

### Architecture (v5)

Forge is a loop, not a collection of agents:

```
objective → plan → execute → learn → [inform next plan]
```

```
/forge "Add OAuth support"
  ↓
forge:planner                         ← VERIFICATION-FIRST PLANNING
  │ (reads project, queries memory,
  │  decomposes, self-validates)
  ↓
[confidence gate: PROCEED/CONFIRM/CLARIFY]
  ↓
forge:orchestrator                    ← FLOW WITH OBSERVATION
  │ (delegates to tether, tracks metrics,
  │  surfaces concerning trends)
  ↓
tether:tether-orchestrator → per-task execution
  ↓
forge:synthesizer                     ← PATTERN CRYSTALLIZATION
  │ (extracts patterns, writes retrospective,
  │  receives campaign metrics)
  ↓
memory (lattice + synthesis.json)     ← SUBSTRATE
  │
  └──────────────────────────────────→ [informs next planning]
```

| Agent                  | Purpose                        | Model   |
| ---------------------- | ------------------------------ | ------- |
| `forge:forge-orchestrator` | Flow with observation      | inherit |
| `forge:planner`        | Verification-first planning    | inherit |
| `forge:synthesizer`    | Pattern crystallization        | inherit |
| `forge:scout`          | Proactive suggestions          | haiku   |

Three core agents + one optional. Capability emerges from the loop.

### Commands

| Command | Purpose |
|---------|---------|
| `/forge <objective>` | Start or resume campaign |
| `/forge:status` | Campaign + active workspace status |
| `/forge:learn` | Force synthesis manually |
| `/forge:scout` | Get proactive suggestions for what to work on |

### State

```
.forge/
├── campaigns/
│   ├── active/      # Current campaigns
│   └── complete/    # Finished campaigns
└── synthesis.json   # Meta-patterns
```

### Example

```bash
# Start a campaign
/forge "Add OAuth support with Google and GitHub"
# Creating campaign: add-oauth-support
# Planning tasks...
#   1. oauth-models
#   2. google-provider
#   3. github-provider
#   4. callback-handling
#   5. session-integration
# Querying precedent...
# Delegating to tether...

# Check status
/forge:status
# Campaign: add-oauth-support (3/5 tasks)
#   [+] 015_oauth-models
#   [+] 016_google-provider
#   [~] 017_github-provider (current)
#   [ ] 018_callback-handling
#   [ ] 019_session-integration

# Resume work
/forge
# Resuming campaign: add-oauth-support
# Next task: github-provider

# Get proactive suggestions
/forge:scout
# Scout Report:
# ### Immediate
# 1. Campaign "add-oauth-support" has 2 pending tasks → /forge
# ### Opportunities
# 2. Pattern #pattern/retry-backoff (net +3) untested in API domain
# ### Warnings
# 3. Pattern #pattern/jwt-storage has net -2 signals
```

### v2 Capabilities

**Critic (Multi-Agent Consensus)**

Before execution, critic reviews the planner's task breakdown:
- Checks scope, ordering, and dependencies
- Queries lattice for contradicting precedent
- Returns APPROVE or OBJECT with actionable feedback
- Max 2 revision cycles before human arbitration

**Semantic Memory**

Lattice now expands queries conceptually:
```bash
/lattice auth
# Expands to: auth, authentication, session, login, credential, token, identity, oauth, jwt
# Finds #pattern/session-token-flow even though "auth" isn't in the name
```

Workspace files can capture rationale:
```markdown
#pattern/session-token-flow
Rationale: Use refresh tokens to maintain sessions without re-authentication
Concepts: authentication, session, token, refresh
Failure modes: Token theft if cookies not httpOnly; refresh race conditions
```

**Scout (Initiative)**

Surface work proactively instead of waiting for commands:
```bash
/forge:scout
```

Scout checks:
- Pending campaign tasks
- Patterns with negative signals
- Stale workspace files
- Synthesis opportunities (3+ campaigns complete)

Returns prioritized suggestions with a recommended next action.

### Verification in the Loop

Every task carries its verification criteria:
```markdown
1. **oauth-models**: Define OAuth data structures
   Delta: src/auth/types.ts
   Depends: none
   Done when: Types compile, tests pass
   Verify: npm run typecheck && npm test src/auth
```

Build runs verification before completing. Failed verification triggers retry loop (max 3 attempts).

`/forge:status` shows campaign health:
```
Tasks: 3/5
  [+] 015_oauth-models (verified)
  [+] 016_google-provider (verified)
  [~] 017_github-provider (current)
      Verify: npm test src/auth/github

Metrics: 2/2 verified first attempt
```

Synthesizer receives campaign metrics for retrospective:
- Verification pass rates
- Revision counts
- Precedent usefulness

### v5 Philosophy: Emergent Simplicity

v5 consolidates v4's capabilities into fewer, more capable units.

**Verification First**

Planner's first act is understanding how the project proves correctness. Verification landscape shapes ALL task design - not discovered per-task, but architected from start.

**Full Context Planning**

Planner reads project files, queries memory, decomposes objective, and self-validates - all in one pass with full context. No delegation to specialists, no summary loss.

**Flow with Observation**

Orchestrator tracks campaign metrics inline (verification success rate, revision rate, precedent usefulness). Surfaces concerning trends to user without blocking. Metrics flow to synthesizer for retrospective.

**Confidence Routing**

Planner signals confidence: PROCEED (execute immediately), CONFIRM (show plan, await approval), CLARIFY (need more input). Orchestrator routes by signal - no deliberation.

### Why Forge

| Ralph Wiggum | Forge v5 |
|--------------|----------|
| Re-inject same prompt | Verification-first planning → execute → learn |
| No memory between sessions | Lattice + synthesis.json persist patterns |
| Single-session bound | Workspace-based coordination |
| Purely reactive | Scout suggests work proactively |
| Multiple agents, fragmented context | Full context in each unit |
| Per-task verification discovery | Verification shapes all planning |
| Post-hoc analysis | Inline observation, metrics to synthesizer |
| Token burn | Simple units, compound growth |

### Constraints

| Constraint | Meaning |
|------------|---------|
| Delegate over implement | Tether does all work |
| Precedent over discovery | Check lattice first |
| Coordinate over block | Report conflicts, human decides |
| Campaign over sprint | Bounded objectives |

---

## When to Use

`tether` shines when precision matters more than speed, when understanding needs to persist across sessions, and when you want Path explicit before implementation begins. It's the right choice for complex features, architectural changes, and work that will be built upon later.

It's overkill for exploratory prototyping (where you *want* the model to wander), simple one-off queries, and quick mechanical fixes. Know when to reach for it.
