# Helix - Technical Reference

A Claude Code orchestrator with integrated memory that learns from every session.

## Architecture

Helix is prose-driven: SKILL.md contains orchestration logic; Python utilities provide the muscle.

```
┌─────────────────────────────────────────────────────────────┐
│                    SKILL.md (Orchestrator)                  │
│  Judgment: what to explore, what to store, when to override │
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Hook Layer (Python)                      │
│  SessionStart: init venv/db  SubagentStop: extract & feedback│
│  SessionEnd: log summary                                     │
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌────────────┐         ┌────────────┐         ┌────────────┐
│  Explorer  │         │  Planner   │         │  Builder   │
│  (haiku)   │         │  (opus)    │         │  (opus)    │
│  agents/   │         │  agents/   │         │  agents/   │
│ explorer.md│         │ planner.md │         │ builder.md │
└────────────┘         └────────────┘         └────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Utilities                          │
│  lib/memory/core.py  - 6 core primitives (store, recall, etc)│
│  lib/injection.py    - Insight injection for agents          │
│  lib/extraction.py   - Learning extraction from transcripts  │
│  lib/prompt_parser.py - Structured field extraction          │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    .helix/helix.db (SQLite)                 │
│  insight table with embeddings, effectiveness, tags          │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Hooks separate judgment from mechanics. Memory injection, learning extraction, and feedback attribution happen automatically. The orchestrator retains judgment: what to store, when to override feedback, what candidates to keep.

## Agents

Three agents with distinct roles:

| Agent | Model | Purpose | Tools | Context Injection |
|-------|-------|---------|-------|-------------------|
| **Explorer** | Haiku | Parallel reconnaissance | Read, Grep, Glob, Bash | Auto: relevant insights |
| **Planner** | Opus | Task decomposition | Read, Grep, Glob, Bash | Auto: relevant insights |
| **Builder** | Opus | Task execution | Read, Write, Edit, Grep, Glob, Bash | Auto: insights + INJECTED names |

### Explorer (`agents/explorer.md`)

Explores ONE scope as part of a parallel swarm. Returns JSON findings.

Input:
- `scope`: Directory path or "memory"
- `focus`: What to find within scope
- `objective`: User goal for context

Output (JSON):
```json
{
  "scope": "src/api/",
  "focus": "route handlers",
  "status": "success",
  "findings": [
    {
      "file": "src/api/routes.py",
      "what": "REST endpoint definitions",
      "action": "modify|create|reference|test",
      "task_hint": "api-routes"
    }
  ],
  "framework": {"detected": "FastAPI", "confidence": "HIGH", "evidence": "..."},
  "patterns_observed": ["dependency injection", "..."]
}
```

Explorer results written to `.helix/explorer-results/{agent_id}.json` by SubagentStop hook.

### Planner (`agents/planner.md`)

Decomposes objective into task DAG using Claude Code's native Task system.

Input:
- `objective`: What to build
- `exploration`: Merged explorer findings

Output:
```
PLAN_SPEC:
001: task-abc123 | Setup authentication service
002: task-def456 | Add login routes | blocks: [001]

PLAN_COMPLETE: 2 tasks
```

Or clarification request:
```json
{"decision": "CLARIFY", "questions": ["..."]}
```

### Builder (`agents/builder.md`)

Executes a single task. Reports DELIVERED or BLOCKED.

Input:
- `TASK_ID`: Unique task identifier
- `TASK`: What to build
- `OBJECTIVE`: Overall objective for context
- `VERIFY`: Command to prove success
- `INSIGHTS`: Injected context with effectiveness scores
- `INJECTED`: List of insight names for feedback tracking

Output:
```
DELIVERED: <one-line summary>
```
Or:
```
BLOCKED: <reason>
TRIED: <what attempted>
ERROR: <message>
```

Optional insight output:
```
INSIGHT: {"content": "When X, do Y because Z", "tags": ["pattern"]}
```

## Hook System

Helix uses Claude Code hooks (Python) for invisible learning operations.

### SessionStart Hooks

**Files:** `scripts/init.sh`, `scripts/setup-env.sh`

Two hooks run at session start:
1. **init.sh**: Initializes the SQLite database, creates `.helix/` directory structure, sets up Python venv, installs dependencies
2. **setup-env.sh**: Writes `plugin_root` file for subagents, sets PYTHONPATH/HELIX_DB_PATH in CLAUDE_ENV_FILE, runs health check

### SubagentStop Hook

**File:** `lib/hooks/extract_learning.py`

Triggered when any `helix:helix-*` agent completes. Processes transcripts for:

1. **Insight extraction**: Looks for `INSIGHT: {"content": "...", "tags": [...]}` or derives from DELIVERED/BLOCKED
2. **Outcome detection**: Parses DELIVERED/BLOCKED markers
3. **Feedback application**: Updates effectiveness of injected insights via EMA
4. **Result persistence**: Writes explorer findings to `.helix/explorer-results/`, task status to `.helix/task-status.jsonl`

**Feedback formula (EMA):**
```
new_effectiveness = old_effectiveness × 0.9 + outcome_value × 0.1
outcome_value = 1.0 (delivered) | 0.0 (blocked)
```

### SessionEnd Hook

**File:** `lib/hooks/session_end.py`

Runs when session ends:
- Counts pending learning queue items
- Logs session summary to `.helix/session.log`
- Cleans up queue files older than 7 days

### State Files

| File/Directory | Purpose | Lifecycle |
|----------------|---------|-----------|
| `.helix/injection-state/` | Tracks injected insights per task | Created on inject, used for audit |
| `.helix/explorer-results/` | Explorer findings by agent ID | Created on SubagentStop |
| `.helix/task-status.jsonl` | Task outcomes for orchestrator | Append-only, JSONL format |
| `.helix/session.log` | Session event log | Append-only |
| `.helix/extraction.log` | Learning extraction diagnostics | Append-only |

## Prompt Parser (`lib/prompt_parser.py`)

Parses structured fields from Task prompts for hook injection.

**Recognized Fields:**
- Explorer: `SCOPE`, `FOCUS`, `OBJECTIVE`
- Planner: `OBJECTIVE`, `EXPLORATION`
- Builder: `TASK_ID`, `TASK`, `OBJECTIVE`, `VERIFY`, `INSIGHTS`, `INJECTED`
- Control: `NO_INJECT` (skip injection if "true")

**Functions:**
```python
parse_prompt(prompt)           # → dict with parsed fields
detect_agent_type(prompt)      # → "explorer" | "planner" | "builder"
should_inject(prompt)          # → False if NO_INJECT: true
extract_*_params(prompt)       # → agent-specific parameters
```

## Memory System

### Insight Model

Single `insight` table stores all learned knowledge:

| Field | Type | Description |
|-------|------|-------------|
| name | TEXT | Unique kebab-case identifier |
| content | TEXT | "When X, do Y because Z" format |
| embedding | BLOB | 384-dim all-MiniLM-L6-v2 |
| effectiveness | REAL | 0.0-1.0, starts at 0.5 (neutral) |
| use_count | INTEGER | Number of times used in feedback |
| tags | TEXT | JSON array for categorization |
| created_at | TEXT | ISO timestamp |
| last_used | TEXT | ISO timestamp of last feedback |

**Semantic deduplication:** New insights are compared against existing embeddings. If cosine similarity ≥ 0.85, the existing insight gets a use_count bump instead of creating a duplicate.

### Primitives (`lib/memory/core.py`)

**6 Core Primitives:**
```python
store(content, tags)              # → {"status": "added"|"merged", "name": "..."}
recall(query, limit, min_eff)     # → [insights with _score, _relevance, _recency]
get(name)                         # → single insight dict
feedback(names, outcome)          # → update effectiveness via EMA
decay(unused_days)                # → decay dormant insights toward 0.5
prune(min_eff, min_uses)          # → remove low performers
health()                          # → system status
```

### Scoring Formula

```
score = (0.5 × relevance) + (0.3 × effectiveness) + (0.2 × recency)

relevance = cosine_similarity(query_embedding, insight_embedding)
effectiveness = 0.0-1.0 (stored directly, updated via EMA)
recency = 2^(-days_since_use / 14)
```

**Score weights** (`SCORE_WEIGHTS` in core.py):
```python
{'relevance': 0.5, 'effectiveness': 0.3, 'recency': 0.2}
```

### Feedback via EMA

```python
new_effectiveness = old_effectiveness * 0.9 + outcome_value * 0.1
outcome_value = 1.0 if outcome == "delivered" else 0.0
```

- Starts at 0.5 (neutral)
- Moves toward 1.0 with repeated success
- Moves toward 0.0 with repeated failure
- EMA smoothing prevents single outliers from dominating

### Decay and Pruning

**Decay** (`decay(unused_days=30)`):
- Affects insights not used in `unused_days`
- Moves effectiveness toward 0.5 by 10%: `eff = eff * 0.9 + 0.5 * 0.1`

**Prune** (`prune(min_effectiveness=0.25, min_uses=3)`):
- Removes insights with effectiveness < threshold
- Only affects insights with at least `min_uses` to ensure fair evaluation

## Injection System (`lib/injection.py`)

Single injection function builds context for any agent:

```python
inject_context(objective, limit=5, task_id=None)
# Returns: {
#   "insights": ["[75%] When X, do Y", ...],
#   "names": ["insight-name-1", ...]
# }
```

**Functions:**
```python
inject_context(objective, limit, task_id)  # Core injection
format_prompt(task_id, task, objective, verify, insights, injected_names)  # Builder prompt
build_agent_prompt(task_data)              # Complete prompt from task dict
```

**Injection state tracking:**
When `task_id` is provided, writes injection state to `.helix/injection-state/{task_id}.json` for audit trail.

## Extraction System (`lib/extraction.py`)

Single extraction function parses any agent transcript:

```python
process_completion(transcript, agent_type)
# Returns: {
#   "insight": {"content": "...", "tags": [...]} | None,
#   "outcome": "delivered" | "blocked" | "unknown",
#   "injected": ["name1", "name2"]
# }
```

**Functions:**
```python
extract_insight(transcript)         # → {"content": "...", "tags": [...]} | None
extract_outcome(transcript)         # → "delivered" | "blocked" | "unknown"
extract_injected_names(transcript)  # → ["name1", "name2"]
process_completion(transcript, agent_type)  # Combined extraction
```

**Insight extraction priority:**
1. Explicit: `INSIGHT: {"content": "...", "tags": [...]}`
2. Derived from DELIVERED with task context
3. Derived from BLOCKED with error context

## Database Schema

SQLite database at `.helix/helix.db` (WAL mode, write lock for safe writes):

```sql
-- Schema versioning
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

-- Insight storage
CREATE TABLE insight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,                    -- 384-dim all-MiniLM-L6-v2
    effectiveness REAL DEFAULT 0.5,    -- 0.0-1.0
    use_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    last_used TEXT,
    tags TEXT DEFAULT '[]'             -- JSON array
);

CREATE INDEX idx_insight_name ON insight(name);
```

## CLI Reference

### Memory Operations

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store insight
python3 "$HELIX/lib/memory/core.py" store --content "When X, do Y because Z" --tags '["pattern"]'

# Recall by semantic similarity
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --min-effectiveness 0.3

# Get single insight
python3 "$HELIX/lib/memory/core.py" get "insight-name"

# Apply feedback
python3 "$HELIX/lib/memory/core.py" feedback --names '["insight-1", "insight-2"]' --outcome delivered

# Decay dormant insights
python3 "$HELIX/lib/memory/core.py" decay --days 30

# Prune low performers
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Health check
python3 "$HELIX/lib/memory/core.py" health
```

### DAG Operations

```bash
# Clear checkpoints
python3 "$HELIX/lib/dag_utils.py" clear

# Detect cycles
python3 "$HELIX/lib/dag_utils.py" detect-cycles --dependencies '{"task-002": ["task-001"]}'

# Check stalled
python3 "$HELIX/lib/dag_utils.py" check-stalled --tasks '[...]'
```

## Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: explore → plan → build → learn → complete |
| `/helix-query <text>` | Search insights by meaning |
| `/helix-stats` | Memory health metrics |

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `HELIX_DB_PATH` | Custom database location | `.helix/helix.db` |
| `HELIX_PLUGIN_ROOT` | Plugin root path | Read from `.helix/plugin_root` |
| `HELIX_PROJECT_DIR` | Project root for hooks | Current working directory |

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| `SCORE_WEIGHTS` | {relevance: 0.5, effectiveness: 0.3, recency: 0.2} | Recall scoring weights |
| `DECAY_HALF_LIFE` | 14 days | Recency score half-life |
| `DUPLICATE_THRESHOLD` | 0.85 | Semantic deduplication threshold |

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── hooks/
│   └── hooks.json            # Hook configuration
├── agents/
│   ├── explorer.md           # Parallel reconnaissance (haiku)
│   ├── planner.md            # Task decomposition (opus)
│   └── builder.md            # Task execution (opus)
├── lib/
│   ├── __init__.py           # Version: 2.0.0
│   ├── hooks/                # Hook implementations (Python)
│   │   ├── __init__.py
│   │   ├── inject_memory.py  # Injection utilities
│   │   ├── extract_learning.py # SubagentStop extraction + feedback
│   │   └── session_end.py    # SessionEnd logging + cleanup
│   ├── memory/
│   │   ├── __init__.py       # Clean exports
│   │   ├── core.py           # 6 primitives (store, recall, get, feedback, decay, prune, health)
│   │   └── embeddings.py     # all-MiniLM-L6-v2
│   ├── db/
│   │   ├── __init__.py
│   │   ├── connection.py     # SQLite singleton, WAL, write_lock
│   │   └── schema.py         # Dataclass definitions
│   ├── injection.py          # Insight injection (inject_context, format_prompt)
│   ├── extraction.py         # Learning extraction (extract_insight, extract_outcome)
│   ├── prompt_parser.py      # Prompt field parsing
│   ├── dag_utils.py          # Cycle detection, stall detection
│   └── wait.py               # Polling utilities
├── scripts/
│   ├── init.sh               # SessionStart: venv/db initialization
│   ├── setup-env.sh          # SessionStart: environment setup
│   └── cleanup-state.sh      # Manual state cleanup
├── skills/
│   ├── helix/
│   │   └── SKILL.md          # Main orchestrator
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
├── tests/
│   ├── conftest.py
│   ├── test_memory_core.py
│   ├── test_injection.py
│   ├── test_extraction.py
│   ├── test_extract_learning.py
│   ├── test_integration.py
│   ├── test_dag_utils.py
│   ├── test_prompt_parser.py
│   └── test_wait.py
└── .helix/                   # Runtime (created on first use)
    ├── helix.db              # SQLite database
    ├── plugin_root           # Plugin path for sub-agents
    ├── session.log           # Session event log
    ├── extraction.log        # Extraction diagnostics
    ├── injection-state/      # Injection tracking by task_id
    ├── explorer-results/     # Explorer findings by agent_id
    └── task-status.jsonl     # Task outcomes (JSONL)
```

## What Helix Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user collaboration tool (single-user, local SQLite)
- A model-agnostic framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
