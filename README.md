# ftl

**forge · tether · lattice**

Orchestration plugins for Claude Code. Campaigns that persist. Tasks that stay bounded. Memory that compounds.

## Introduction

Before Opus 4.5, agentic tools and harnesses focused on working *around* the two worst tendencies of LLMs: scope creep and over-engineering. Coding assistants felt like overeager junior-savants that had to be carefully managed whenever projects became even moderately complex.

Opus 4.5 broke this pattern. If you're reading this, then you've likely felt the shift. We are now living the transformation of LLM agents from spastic assistants to true collaborators.

`ftl` is built on this shift. Three plugins that work together:

- **forge**: Coordinates multi-task campaigns spanning sessions. Decomposes objectives, delegates to tether, learns from outcomes.
- **tether**: Executes single tasks with precision. Anchors work to `Path` (what data transforms) and `Delta` (what files change).
- **lattice**: Remembers decisions. Indexes workspace files, tracks pattern success via signals, surfaces relevant precedent.

Context still disappears between sessions. `ftl` solves this. Tasks produce workspace files capturing Path, Delta, and the exploration that led there. `lattice` indexes these into a queryable decision graph. `forge` queries this graph before planning new work. Understanding persists because it's actively transformed and structured.

## Overview

```
forge (campaign) → tether (task) → workspace/ → lattice (memory)
      ↑                                              │
      └──────────── queries precedent ───────────────┘
```

| Plugin | Level | Purpose |
|--------|-------|---------|
| **forge** | Campaign | Multi-task objectives spanning sessions |
| **tether** | Task | Single-task execution with Path+Delta anchoring |
| **lattice** | Memory | Queryable decision index with signal evolution |

## Philosophy

`ftl` is built on eight principles:

| Principle | Meaning |
|-----------|---------|
| **Present over future** | Implement current requests, not anticipated needs |
| **Concrete over abstract** | Build specific solutions, not abstract frameworks |
| **Explicit over clever** | Choose clarity over sophistication |
| **Edit over create** | Modify what exists before creating new |
| **Verification-first** | Shape work by starting with proof-of-success |
| **Scope-bounded** | Delta files are explicit so humans can audit agent boundaries |
| **Memory compounds** | Each campaign leaves the system smarter |
| **Escalation as success** | Honest escalation beats confident failure |

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

---

## forge

Coordinates bounded development objectives through campaigns. Not projects (too permanent). Not tasks (too granular). A campaign is a measurable objective spanning multiple tether tasks.

### Architecture

```
objective → plan → execute → learn → [inform next plan]
```

| Agent | Purpose | Model |
|-------|---------|-------|
| `forge:forge-orchestrator` | Campaign coordination and flow | inherit |
| `forge:planner` | Verification-first task decomposition | inherit |
| `forge:reflector` | Failure diagnosis and escalation | inherit |
| `forge:synthesizer` | Cross-campaign meta-learning | inherit |
| `forge:scout` | Proactive work suggestions | haiku |

### Flow

**Planner** starts with verification: "How will we prove this objective is met?" Each task gets:
- Slug and description
- Delta files (explicit scope)
- Dependencies
- Done-when criteria
- Verify command

Planner returns a confidence signal:
- **PROCEED**: Clear verification path, execute immediately
- **CONFIRM**: Sound plan, show for approval first
- **CLARIFY**: Can't establish verification, return questions

**Orchestrator** delegates each task to tether, gates on completion, invokes reflector on failure.

**Reflector** classifies failures:
- Execution (code wrong) → RETRY with fix
- Approach (design wrong) → RETRY with new strategy
- Scope/Environment (external issue) → ESCALATE to human

**Synthesizer** extracts meta-patterns after campaign completion: which patterns work together, what replaced what, what transfers across domains.

### State

```
.forge/
├── campaigns/
│   ├── active/      # Current campaigns
│   └── complete/    # Finished campaigns
└── synthesis.json   # Cross-campaign meta-patterns
```

### Commands

| Command | Purpose |
|---------|---------|
| `/forge <objective>` | Start or resume campaign |
| `/forge:status` | Campaign + workspace status |
| `/forge:learn` | Force synthesis manually |
| `/forge:scout` | Get proactive suggestions |

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
#   [+] 015_oauth-models (verified)
#   [+] 016_google-provider (verified)
#   [~] 017_github-provider (current)
#   [ ] 018_callback-handling
#   [ ] 019_session-integration

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

---

## tether

Executes single tasks with precision. Anchors work to two concepts that prevent scope creep:

- **Path**: The core data flow touched by a request. Shows transformation with arrows.
- **Delta**: The minimal, targeted changes. File-level scope boundary.

### Architecture

```
[Assess] → route → [Anchor] → Path+Delta → [Build] → complete → [Reflect]
```

| Agent | Purpose | Model |
|-------|---------|-------|
| `tether:assess` | Route: full / direct / clarify | haiku |
| `tether:anchor` | Establish Path, Delta, Thinking Traces | inherit |
| `tether:code-builder` | Implement within constraints | inherit |
| `tether:reflect` | Extract patterns (conditional) | inherit |

### Flow

**Assess** makes a single routing decision:
- **full**: Path needs discovery or knowledge should persist → create workspace file
- **direct**: Path is obvious, work is ephemeral → execute immediately
- **clarify**: Request is ambiguous → ask user

**Anchor** explores the codebase and creates a workspace file with:
- Path (data transformation)
- Delta (file scope)
- Verify (test command if discoverable)
- Thinking Traces (exploration findings)

**Build** implements exactly what was anchored. Test-first, edit-over-create, no abstractions unless requested. Pre-completion scope check ensures all touched files are within Delta.

**Reflect** extracts reusable patterns when decision markers appear in Thinking Traces. Tags like `#pattern/`, `#constraint/`, `#decision/` enable future retrieval.

### Workspace Files

Files live in `workspace/`. Naming is structural:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

- `NNN`: Sequence (001, 002...)
- `status`: active, complete, blocked
- `_from-NNN`: Lineage (builds on prior task)

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [file patterns]
Verify: [command or "none discovered"]
Branch: [git branch]

## Thinking Traces
[exploration findings, decisions, dead ends]

## Delivered
[filled by Build agent on completion]

#pattern/name #constraint/type
```

### Commands

| Command | Purpose |
|---------|---------|
| `/tether:workspace` | Query workspace state and lineage |
| `/tether:anchor` | Create workspace file manually |
| `/tether:close` | Complete task manually |
| `/tether:stats` | Workspace statistics |

### Example

```bash
# Query workspace
/tether:workspace
# 12 files: 8 complete, 3 active, 1 blocked
# Depth distribution: 1→6, 2→4, 3→2

# View lineage
/tether:workspace 003
# [+] 001_init-setup
#   └─[+] 003_auth-refactor
#       └─[~] 007_session-timeout (active)

# List all extracted patterns
/tether:workspace tags
# #pattern/session-token-flow (3 uses)
# #pattern/retry-backoff (2 uses)
# #constraint/no-jwt-cookies (1 use)
```

---

## lattice

Semantic memory for tether workspaces. Indexes decisions, tracks pattern success, surfaces relevant precedent.

### Data Model

```
.lattice/
├── index.json    # Decision records with full context
├── edges.json    # Relationships (lineage, patterns, file impact)
├── signals.json  # Outcome tracking (+/-)
└── vectors/      # Embeddings for semantic search (optional)
```

The graph treats decisions as nodes and patterns as edges. Lineage chains, pattern usage, and file impact all become queryable relationships.

### Agents

| Agent | Purpose | Model |
|-------|---------|-------|
| `lattice:miner` | Extract and index decisions from workspace | haiku |
| `lattice:surface` | Find relevant decisions for a topic | haiku |

### Hybrid Retrieval

Lattice combines exact matching with semantic similarity:

```
score = recency_factor × signal_factor × semantic_factor
```

- **Recency**: Newer decisions weighted higher (30-day half-life)
- **Signals**: Positively-signaled patterns get boosted; negative signals suppress
- **Semantic**: Embedding similarity when sentence-transformers available

Query expansion maps related concepts: `auth` finds decisions tagged with `session`, `token`, `credential`, `oauth`.

### Commands

| Command | Purpose |
|---------|---------|
| `/lattice <topic>` | Surface relevant decisions |
| `/lattice:mine` | Build decision index |
| `/lattice:decision NNN` | Full decision record with traces |
| `/lattice:lineage NNN` | Decision ancestry chain |
| `/lattice:trace #pattern/X` | Find decisions using a pattern |
| `/lattice:impact <file>` | Find decisions affecting a file |
| `/lattice:age [days]` | Find stale decisions |
| `/lattice:signal +/- #pattern/X` | Mark pattern outcome |

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

# Trace pattern usage
/lattice:trace #pattern/session-token-flow
# Decisions using #pattern/session-token-flow:
#   [015] auth-refactor (3d, complete)
#   [023] session-timeout (1d, complete)

# Track outcomes
/lattice:signal + #pattern/session-token-flow
# Signal added: #pattern/session-token-flow → net 2

# Find what touched a file
/lattice:impact src/auth
# [015] auth-refactor
# [023] session-timeout
# [027] oauth-integration
```

### Weighting

Results rank by recency and signal history. Recent work surfaces first. Patterns marked successful (`/lattice:signal +`) get weighted higher. Patterns that caused problems (`/lattice:signal -`) fade. The graph learns which approaches work in your codebase.

---

## Integration

The three plugins operate in a feedback loop:

```
User objective
     ↓
forge:planner ─────────────────┐
     │                         │
     │  queries precedent      │
     ↓                         ↓
lattice ← indexes ← workspace/ ← tether
     │                              │
     └── signals inform ranking ────┘
```

- **forge** coordinates campaigns, queries lattice for precedent, delegates tasks to tether
- **tether** executes tasks, writes workspace files with Path+Delta+Traces
- **lattice** indexes workspace files, tracks signals, surfaces relevant decisions

Each completed task makes the system smarter. Patterns emerge, get signaled, influence future planning.

---

## When to Use

**forge**: Complex features spanning multiple tasks. Work that continues across sessions. Objectives needing decomposition and verification planning.

**tether**: Single focused tasks. Architectural changes. Features where Path clarity matters. Work that should persist as precedent.

**lattice**: When workspace has accumulated enough decisions. Querying what you've done before. Tracking which patterns succeed or fail.

**Skip all**: Exploratory prototyping where you want the model to wander. Simple one-off queries. Quick mechanical fixes. Know when to reach for these tools.
