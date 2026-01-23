# Helix - Comprehensive Reference

A Claude Code orchestrator with integrated memory that learns from every session.

> This document contains the complete technical reference for helix. For a quick overview, see the [README](../helix/README.md).

## Introduction

Helix unifies orchestration and memory into a single system. Previous designs separated these concerns—arc for memory, helix for orchestration—but the integration points created friction: subprocess calls, discovery failures, silent degradation.

The current design eliminates this friction. Memory operations are direct Python imports. The feedback loop closes within a single function call. No external dependencies, no subprocess overhead, no configuration discovery.

## Philosophy

| Principle | Meaning |
|-----------|---------|
| **Feedback closes the loop** | Every task completion updates memory effectiveness |
| **Verify before claiming success** | No DELIVERED without passing verify command |
| **Delta scope is hard** | Builders cannot modify files outside their delta |
| **Blocking is success** | Clear blocking info creates learning data |
| **UTILIZED must be honest** | False positives corrupt the feedback signal |
| **Edit over create** | Modify what exists before creating something new |

## Quick Start

```bash
# Add the crinzo-plugins marketplace
claude plugin marketplace add https://github.com/enzokro/crinzo-plugins

# Install helix
claude plugin install helix@crinzo-plugins
```

Or from inside Claude Code:
```bash
/plugin marketplace add https://github.com/enzokro/crinzo-plugins
/plugin install helix@crinzo-plugins
```

Optional for semantic search:
```bash
pip install sentence-transformers
```

## Development Loop

```
/helix <objective>
    │
    ▼
┌─────────────────────────────────────┐
│  EXPLORER (haiku, 6 tools)          │
│  structure │ patterns │ memory │ targets
└─────────────────────────────────────┘
    │
    ▼ exploration (database)
┌─────────────────────────────────────┐
│  PLANNER (opus)                     │
│  Decompose → Dependencies → Budget  │
└─────────────────────────────────────┘
    │
    ▼ task DAG + native Task system
┌─────────────────────────────────────┐
│  BUILDER (opus, per-task budget)    │
│  Read → Implement → Verify → Report │
└─────────────────────────────────────┘
    │
    ▼ DELIVERED/BLOCKED + UTILIZED
┌─────────────────────────────────────┐
│  OBSERVER (opus)                    │
│  Extract failures │ Chunk patterns  │
└─────────────────────────────────────┘
    │
    ▼ memory.feedback(utilized, injected)
```

**Explorer** gathers codebase context. **Planner** decomposes into a task DAG. **Builders** execute tasks with memory injection. **Observer** extracts learning. **Feedback** updates effectiveness scores.

## Agents

Four agents with distinct roles:

| Agent | Model | Role | Budget |
|-------|-------|------|--------|
| **Explorer** | Haiku | Codebase reconnaissance | 6 |
| **Planner** | Opus | Decompose objectives into tasks | unlimited |
| **Builder** | Opus | Execute tasks within constraints | 5-9 |
| **Observer** | Opus | Extract patterns and failures | 10 |

### Explorer (haiku, budget: 6)

Gathers:
- **Structure**: Directories, entry points, test patterns
- **Patterns**: Framework detection, idioms
- **Memory**: Relevant failures and patterns from history
- **Targets**: Files and functions to modify

Output: JSON with structure, patterns, memory, targets.

### Planner (opus, unlimited)

Creates task DAG with:
- `seq` — Execution order identifier (001, 002, ...)
- `slug` — Human-readable name
- `objective` — What to accomplish
- `delta` — Files the builder may modify (hard constraint)
- `verify` — Command to verify completion
- `depends` — Task dependencies (none, or comma-separated seqs)
- `budget` — Tool calls allocated (5-9)

**Decision gates**:
- `PROCEED` — Sufficient information to plan
- `CLARIFY` — Need answers before proceeding

Registers tasks in Claude Code's native Task system (visible via Ctrl+T).

### Builder (opus, budget: 5-9)

Execution flow:
```
READ → PLAN → IMPLEMENT → VERIFY → REPORT
```

**Constraints enforced**:
- Delta scope is hard — cannot modify files outside delta
- Budget is hard — must complete or block when exhausted
- Idiom enforcement — violations block even if tests pass

**Output**:
- `DELIVERED: <summary>` + `UTILIZED: [memories that helped]`
- `BLOCKED: <reason>` + `UTILIZED: [memories that helped despite block]`

**Metacognition**: After 3 failed attempts with similar approach → BLOCK with analysis, don't retry.

### Observer (opus, budget: 10)

Extracts:
- **Failures** from blocked workspaces (trigger + resolution)
- **Patterns** from successful workspaces via SOAR chunking
- **Relationships** between memories (co_occurs, causes, solves)

Closes the feedback loop:
```python
feedback(utilized, injected)
# utilized memories: helped++
# injected-but-unused: failed++
```

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: explore → plan → build → observe |
| `/helix-query <text>` | Search memory by meaning |
| `/helix-stats` | Memory health metrics |

## Workspace Format

Tasks produce workspace records in `.helix/helix.db`. Each workspace contains:

```yaml
task_seq: "001"
task_slug: "impl-auth"
objective: "Implement JWT authentication"
delta: ["src/auth.py", "tests/test_auth.py"]
verify: "pytest tests/test_auth.py -v"
budget: 7
framework: "fastapi"
idioms:
  required: ["Use Depends() for auth"]
  forbidden: ["Store passwords in plain text"]
failures: [...]  # Injected memories to avoid
patterns: [...]  # Injected memories to apply
lineage:
  parents: [{seq, slug, delivered}]  # What parent tasks delivered
```

## Memory System

Unified semantic memory with effectiveness tracking.

### Scoring Formula

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)

relevance = cosine_similarity(query_embedding, memory_embedding)
effectiveness = helped / (helped + failed)  # default 0.5 if no feedback
recency = 2^(-days_since_use / 7)           # ACT-R decay, 7-day half-life
```

Memories that help rise in ranking. Memories that don't help sink.

### Memory Types

| Type | Purpose | Example |
|------|---------|---------|
| **failure** | Error to avoid | "ImportError when using circular imports" → "Move shared types to separate module" |
| **pattern** | Technique to apply | "FastAPI auth" → "Use Depends() with JWT validation" |

### Operations

```python
# Store
store(trigger, resolution, type="failure", source="")
# → {"status": "added", "name": "import-error-circular", "reason": ""}

# Recall (semantic search)
recall(query, type=None, limit=5, min_effectiveness=0.0)
# → [{"name": "...", "trigger": "...", "_score": 0.73, ...}]

# Feedback (THE critical function)
feedback(utilized=["mem-1"], injected=["mem-1", "mem-2"])
# → {"helped": 1, "unhelpful": 1, "missing": []}

# SOAR chunking
chunk(task_objective, outcome="success", approach="...")
# → {"status": "added", "name": "task-auth-impl", "reason": ""}

# Graph relationships
relate(from_name, to_name, rel_type, weight=1.0)
connected(name, max_hops=2)
```

### CLI Interface

```bash
# Store
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py store \
    --trigger "situation" --resolution "action" --type failure

# Recall
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py recall "query" --limit 5

# Feedback
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py feedback \
    --utilized '["mem-1"]' --injected '["mem-1", "mem-2"]'

# Health
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py health

# Maintenance
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py consolidate  # merge similar
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py prune        # remove ineffective
python3 $HELIX_PLUGIN_ROOT/lib/memory/core.py decay        # find dormant
```

### Semantic Deduplication

85% cosine similarity threshold prevents near-duplicates:
- Below 0.85: Stored as separate entry
- At or above 0.85: Merged with existing entry

### Embedding Model

Uses `sentence-transformers all-MiniLM-L6-v2` for 384-dimensional embeddings. Falls back to effectiveness-based ranking when unavailable.

### Metacognition

The `meta.py` module provides approach assessment:

```python
assess_approach(task_objective, current_approach, memories)
# → {"recommendation": "continue" | "pivot" | "escalate",
#    "reason": "...", "attempts": 3, "suggested_pivot": "..."}
```

Detects stuck loops (same approach failing repeatedly) and suggests pivots based on memory patterns.

## Database Schema

Single SQLite database at `.helix/helix.db`:

```sql
-- Memory layer
CREATE TABLE memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('failure', 'pattern')),
    trigger TEXT NOT NULL,
    resolution TEXT NOT NULL,
    embedding BLOB,
    helped INTEGER DEFAULT 0,
    failed INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used TEXT,
    source TEXT DEFAULT ''
);

CREATE TABLE memory_edge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_name TEXT NOT NULL,
    to_name TEXT NOT NULL,
    rel_type TEXT NOT NULL,
    weight REAL DEFAULT 1.0,
    created_at TEXT NOT NULL,
    UNIQUE(from_name, to_name, rel_type)
);

-- Orchestration layer
CREATE TABLE exploration (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    objective TEXT NOT NULL,
    data TEXT NOT NULL,  -- JSON
    created_at TEXT NOT NULL
);

CREATE TABLE plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    objective TEXT NOT NULL,
    framework TEXT,
    idioms TEXT,  -- JSON
    tasks TEXT NOT NULL,  -- JSON array
    status TEXT DEFAULT 'active',
    created_at TEXT NOT NULL
);

CREATE TABLE workspace (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER,
    task_seq TEXT NOT NULL,
    task_slug TEXT NOT NULL,
    objective TEXT NOT NULL,
    data TEXT NOT NULL,  -- JSON
    status TEXT DEFAULT 'active',
    delivered TEXT DEFAULT '',
    utilized TEXT DEFAULT '[]',  -- JSON array
    created_at TEXT NOT NULL,
    FOREIGN KEY (plan_id) REFERENCES plan(id)
);
```

WAL mode enabled for concurrent reads. Write lock for safe writes.

## Configuration Constants

| Constant | Value | Location | Purpose |
|----------|-------|----------|---------|
| `DUPLICATE_THRESHOLD` | 0.85 | core.py | Semantic deduplication |
| `DECAY_HALF_LIFE_DAYS` | 7 | core.py | Recency scoring |
| `SCORE_WEIGHTS['relevance']` | 0.5 | core.py | Scoring formula |
| `SCORE_WEIGHTS['effectiveness']` | 0.3 | core.py | Scoring formula |
| `SCORE_WEIGHTS['recency']` | 0.2 | core.py | Scoring formula |

## Hooks

| Hook | Trigger | Script | Purpose |
|------|---------|--------|---------|
| SessionStart | Session begins | `setup-env.sh` | Initialize database, set env vars |
| PreToolUse | Edit/Write | `inject-context.py` | Inject relevant memories |

**inject-context.py**: Queries memory for relevant failures/patterns before file modifications. Injects via `additionalContext`. Requests UTILIZED reporting.

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── agents/
│   ├── explorer.md           # Context gathering (haiku)
│   ├── planner.md            # Task decomposition (opus)
│   ├── builder.md            # Task execution (opus)
│   └── observer.md           # Learning extraction (opus)
├── lib/
│   ├── memory/
│   │   ├── __init__.py       # Clean exports
│   │   ├── core.py           # store, recall, feedback, chunk, etc.
│   │   ├── embeddings.py     # Semantic search
│   │   └── meta.py           # Metacognition
│   ├── db/
│   │   └── connection.py     # SQLite with unified schema
│   ├── exploration.py        # Exploration storage
│   ├── plan.py               # Plan management
│   └── workspace.py          # Task execution context
├── scripts/
│   ├── setup-env.sh          # SessionStart hook
│   └── inject-context.py     # PreToolUse hook
├── skills/
│   ├── helix/
│   │   └── SKILL.md          # Main orchestrator
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
└── README.md
```

## What's Automated vs. What's Documented

| Layer | How It Works | Reliability |
|-------|--------------|-------------|
| **Python Infrastructure** | Deterministic code | Guaranteed |
| **Agent Instructions** | Claude following markdown specs | Probabilistic |

**Automated (100% reliable):**
- Semantic memory retrieval and scoring
- Feedback loop closure (workspace.complete → memory.feedback)
- Embedding generation and cosine similarity
- Database transactions (ACID compliance)
- Memory deduplication (85% threshold)
- Recency decay calculation
- PreToolUse memory injection

**Documented (agent judgment):**
- Pattern extraction decision (scores are guidance)
- Error match determination (similarity + applicability)
- Idiom compliance checking
- UTILIZED reporting (depends on honest agent)
- CLARIFY decision gate in Planner
- Retry vs. block decision

## When to Use

**Use helix when:**
- Complex multi-step work requiring exploration first
- Similar work has been done before (leverage learned context)
- Verification needed at each phase
- Framework-specific development with idiom enforcement

**Skip helix when:**
- Simple single-file changes
- Exploratory prototyping
- Quick one-offs with no future value
- Work that doesn't benefit from learned context

## What Helix Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user collaboration tool (single-user, local SQLite)
- A model-agnostic framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
