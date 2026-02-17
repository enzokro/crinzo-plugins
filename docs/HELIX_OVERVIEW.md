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
│                    Hook Layer (4 hooks)                     │
│  SessionStart: init venv/env   SubagentStart: inject memory│
│  SubagentStop: extract & feedback   SessionEnd: decay/prune│
└─────────────────────────────────────────────────────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌────────────┐         ┌────────────┐         ┌────────────┐
│  Explorer  │         │  Planner   │         │  Builder   │
│  (sonnet)  │         │  (opus)    │         │  (opus)    │
│  agents/   │         │  agents/   │         │  agents/   │
│ explorer.md│         │ planner.md │         │ builder.md │
└────────────┘         └────────────┘         └────────────┘
        │                      │                      │
        ▼                      ▼                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Python Utilities (lib/)                  │
│  memory/core.py     - 8 primitives (store, recall, etc.)   │
│  memory/embeddings.py - snowflake-arctic-embed-m-v1.5      │
│  injection.py       - Insight injection for agents         │
│  extraction.py      - Learning extraction from transcripts │
│  build_loop.py      - DAG operations and wave management   │
└─────────────────────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                    .helix/helix.db (SQLite, WAL)           │
│  insight table: embeddings, effectiveness, causal_hits     │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Hooks separate judgment from mechanics. Memory injection, learning extraction, and feedback attribution happen automatically. The orchestrator retains judgment: what to store, when to override feedback, what candidates to keep.

## Orchestrator Phases

Defined in `skills/helix/SKILL.md`. Six phases:

```
EXPLORE → RECALL → PLAN → BUILD (loop) → LEARN → COMPLETE
```

| Phase | Agent | Purpose |
|-------|-------|---------|
| **EXPLORE** | Explorer swarm (sonnet, parallel) | Map codebase structure into findings |
| **RECALL** | Orchestrator (no agent) | Recall strategic insights, synthesize into CONSTRAINTS |
| **PLAN** | Planner (opus) | Decompose objective into task DAG, respecting CONSTRAINTS |
| **BUILD** | Builder swarm (opus, parallel waves) | Execute tasks; stall recovery uses recall too |
| **LEARN** | Orchestrator + user | Observe patterns, ask user, store validated insights |
| **COMPLETE** | Orchestrator | Summarize deliveries, blocks, stored insights |

**RECALL** is the orchestrator's strategic memory layer. After exploration, the orchestrator calls `core.py recall` with the objective, then reasons about what the insights mean for *orchestration*—not tactical advice (hooks handle that), but decomposition constraints, verification requirements, risk areas, and sequencing hints. These are synthesized into a `CONSTRAINTS` block passed to the planner. On cold start (no insights), CONSTRAINTS is omitted; the planner operates as before with no degradation. Skipped on fast path (single-file changes).

**Two-level memory injection:**
- **Strategic (RECALL phase):** Orchestrator → `CONSTRAINTS` → planner prompt. Informs *how to decompose*.
- **Tactical (SubagentStart hook):** Hook → `INSIGHTS` → builder/planner prompt. Informs *how to execute*.

## Agents

Three agents with distinct roles:

| Agent | Model | Purpose | Tools | Hook Injection |
|-------|-------|---------|-------|----------------|
| **Explorer** | Sonnet | Parallel reconnaissance | Read, Grep, Glob, Bash | None (no SubagentStart) |
| **Planner** | Opus | Task decomposition | Read, Grep, Glob, Bash | SubagentStart: insights |
| **Builder** | Opus | Task execution | Read, Write, Edit, Grep, Glob, Bash | SubagentStart: insights + sideband |

### Explorer (`agents/explorer.md`)

Explores ONE scope as part of a parallel swarm. Returns JSON findings.

Input:
- `SCOPE`: Directory path or "memory"
- `FOCUS`: What to find within scope
- `OBJECTIVE`: User goal for context

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
- `OBJECTIVE`: What to build
- `EXPLORATION`: Merged explorer findings
- `CONSTRAINTS` (optional): Strategic constraints from orchestrator's RECALL phase—decomposition patterns, verification requirements, risk areas, sequencing hints from past sessions. Respected unless they directly conflict with the current objective.

Output:
```
PLAN_SPEC:
[
  {"seq": "001", "slug": "setup-models", "description": "...",
   "relevant_files": ["src/models.py"], "blocked_by": [], "verify": "pytest tests/test_models.py"},
  {"seq": "002", "slug": "implement-api", "description": "...",
   "relevant_files": ["src/api/routes.py"], "blocked_by": ["001"], "verify": "pytest tests/test_api.py"}
]

PLAN_COMPLETE: 2 tasks specified
INSIGHT: {"content": "When planning X, structure as Y because Z", "tags": ["architecture"]}
```

Or clarification request:
```json
{"decision": "CLARIFY", "questions": ["..."]}
```

### Builder (`agents/builder.md`)

Executes a single task. Reports DELIVERED, BLOCKED, or PARTIAL.

Input (structured fields):
- `TASK_ID`: Unique task identifier
- `TASK`: What to build
- `OBJECTIVE`: Overall objective for context
- `VERIFY`: Command to prove success
- `RELEVANT_FILES`: Files identified during exploration
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
Or:
```
PARTIAL: <what was completed>
REMAINING: <what still needs doing>
```

Optional insight output:
```
INSIGHT: {"content": "When X, do Y because Z", "tags": ["pattern"]}
```

## Hook System

Four hooks wired in `hooks/hooks.json`:

| Event | Matcher | Command | Timeout |
|-------|---------|---------|---------|
| SessionStart | (all sessions) | `scripts/setup-env.sh` | 120s |
| SubagentStart | `helix:helix-builder\|helix:helix-planner` | `lib/hooks/inject_memory.py` | 15s |
| SubagentStop | `helix:helix-.*` | `lib/hooks/extract_learning.py` | 30s |
| SessionEnd | (all sessions) | `lib/hooks/session_end.py` | default |

### Hook Lifecycle

```
SessionStart (setup-env.sh)
    │  Wipe ephemeral state: injected/, explorer-results/, task-status.jsonl
    │  Ensure venv + dependencies (sentence-transformers)
    │  Persist env vars via CLAUDE_ENV_FILE
    │  Background warmup: embed model pre-load (non-blocking)
    │  Report health status + insight count
    │
    ▼
SubagentStart (inject_memory.py) — builders & planners only
    │  Parse parent transcript (last 50KB) for OBJECTIVE
    │  If orchestrator already injected → skip (return {})
    │  Collect sibling sideband names → cross-agent diversity
    │  recall(objective, suppress_names=already_injected)
    │  Write sideband: .helix/injected/{agent_id}.json
    │    └─ {names, objective, query_embedding (base64)}
    │  Return {additionalContext: formatted insights}
    │
    ▼
Agent executes (explorer, planner, or builder)
    │
    ▼
SubagentStop (extract_learning.py) — all helix agents
    │  Phase 1 (Handoff): Write task-status.jsonl + explorer-results
    │  Phase 2 (Outcome): process_completion() with retry on unknown
    │  Phase 3a: store_insight() — independent error boundary
    │  Phase 3b: read sideband → causal filter → feedback — independent
    │  Phase 3c: log diagnostics — independent
    │
    ▼
SessionEnd (session_end.py)
    │  Delete task-status.jsonl
    │  Clean stale .helix/injected/*.json
    │  decay() — dormant insights drift toward neutral
    │  prune() — remove low performers, orphans, ghosts
    │  Log session summary to session.log
```

### SessionStart Hook

**File:** `scripts/setup-env.sh`

- Resolves plugin root (env var → `.helix/plugin_root` → script dir)
- Wipes session-specific state (task-status, explorer-results, injected/)
- Creates/validates Python venv with `sentence-transformers`
- Persists `PATH`, `PYTHONPATH`, `HELIX_ROOT`, `HELIX_DB_PATH`, `HELIX_PROJECT_DIR` via `CLAUDE_ENV_FILE`
- Runs `core.py health` for status report
- Background `embeddings.py warmup` (pre-loads model into OS page cache)

### SubagentStart Hook

**File:** `lib/hooks/inject_memory.py`

Fires for builders and planners. Parses the parent (orchestrator) transcript to extract the task objective and detect whether the orchestrator already injected insights in the prompt. If already injected, returns `{}` to avoid duplication.

For non-injected agents:
1. Collects already-injected names from sibling sideband files (cross-agent diversity)
2. Recalls insights with `suppress_names` to avoid repeating what siblings received
3. Writes sideband file with insight names, objective, and base64-encoded query embedding
4. Returns `{"additionalContext": "INSIGHTS (from past experience):\n  - [75%] When X..."}`

Cold-start signals:
- `NO_PRIOR_MEMORY: Novel domain.` — zero insights in database
- `NO_MATCHING_INSIGHTS: No matching insights found for this task.` — insights exist but none relevant

### SubagentStop Hook

**File:** `lib/hooks/extract_learning.py`

Fires for all helix agents. Three-phase pipeline where each phase has independent error boundaries:

**Phase 1 — Handoff:** Writes `.helix/task-status.jsonl` (append-only JSONL) and `.helix/explorer-results/{agent_id}.json`. These files are consumed by `build_loop.py` and must succeed even if insight processing fails.

**Phase 2 — Outcome:** Runs `process_completion()` for single-pass extraction. For unknown outcomes with `has_error`, maps to "crashed". Otherwise retries with exponential backoff (0.15s, 0.35s, 0.75s) to handle transcript write race conditions.

**Phase 3 — Learning (three independent boundaries):**
- **3a:** Store extracted insight (`initial_effectiveness=0.35` for derived insights)
- **3b:** Read sideband → merge injected names → resolve task context (prefers sideband objective) → causal filter → apply feedback (crashed → blocked mapping)
- **3c:** Log extraction result with causal ratio

### SessionEnd Hook

**File:** `lib/hooks/session_end.py`

Auto-maintenance: `decay()` moves dormant insights toward neutral, then `prune()` removes low performers. Cleans up `task-status.jsonl` and stale sideband files. Logs session summary to `session.log`.

### Runtime State Files

| File/Directory | Purpose | Written By | Consumed By | Lifecycle |
|----------------|---------|------------|-------------|-----------|
| `.helix/plugin_root` | Plugin installation path | `setup-env.sh` | SKILL.md, agents | Per session |
| `.helix/helix.db` | SQLite database (WAL) | `connection.py` | All memory ops | Persistent |
| `.helix/injected/{agent_id}.json` | Sideband (names + embedding) | `inject_memory.py` | `extract_learning.py` | Read-and-delete |
| `.helix/explorer-results/{agent_id}.json` | Explorer findings | `extract_learning.py` | `build_loop.py` | Per session |
| `.helix/task-status.jsonl` | Builder outcomes | `extract_learning.py` | `build_loop.py` | Per session |
| `.helix/extraction.log` | Injection + extraction diagnostics | Both hooks | Debugging | Persistent |
| `.helix/session.log` | Session lifecycle events | `session_end.py` | Debugging | Persistent |

## Memory System

### Database Schema

SQLite database at `.helix/helix.db` (WAL mode, `busy_timeout=5000` for cross-process safety):

```sql
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE insight (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    embedding BLOB,                    -- 256-dim snowflake-arctic-embed-m-v1.5, f32
    effectiveness REAL DEFAULT 0.5,    -- 0.0-1.0, neutral start
    use_count INTEGER DEFAULT 0,       -- Causal feedback count
    causal_hits INTEGER DEFAULT 0,     -- Causally attributed outcomes
    created_at TEXT NOT NULL,          -- ISO 8601 naive UTC
    last_used TEXT,                     -- Updated on feedback/merge
    last_feedback_at TEXT,             -- Updated on causal feedback only
    tags TEXT DEFAULT '[]'             -- JSON array
);
-- UNIQUE on name provides automatic index; no additional indexes
```

**Schema version:** v10. Migrations in `lib/db/connection.py:_apply_migrations()`. Notable: v8 NULLed all embeddings (model migration), v9 dropped legacy tables, v10 dropped redundant `idx_insight_name`.

### 8 Primitives (`lib/memory/core.py`)

```python
store(content, tags=None, initial_effectiveness=0.5)
    # → {"status": "added"|"merged"|"rejected", "name": str, "reason": str}

recall(query, limit=5, min_effectiveness=0.0, min_relevance=0.35, suppress_names=None)
    # → [insights with _relevance, _effectiveness, _score]

get(name)
    # → single insight dict with parsed tags, or None

feedback(names, outcome, causal_names=None)
    # → {"updated": int, "outcome": str, "causal": int, "eroded": int}

decay(unused_days=30)
    # → {"decayed": int, "threshold_days": int}

prune(min_effectiveness=0.25, min_uses=3)
    # → {"pruned": int, "orphans_cleaned": int, "ghosts_cleaned": int, "remaining": int}

count()
    # → int (total insight count, no numpy import)

health()
    # → {"status": str, "total_insights": int, "by_tag": dict, "effectiveness": dict, ...}
```

**Performance note:** `numpy` is imported locally only in `store()` and `recall()`. Lightweight operations (`count`, `decay`, `feedback`, `prune`, `health`, `get`) avoid the ~100-200ms numpy import tax.

### Scoring Formula

```
score = relevance × (0.5 + 0.5 × effectiveness) × recency
```

| Component | Source | Range |
|-----------|--------|-------|
| `relevance` | Cosine similarity (dot product of L2-normalized vectors) | 0.0-1.0 |
| `effectiveness` | Causal-adjusted: `eff × max(0.3, causal_hits/use_count)` for ≥3 uses | 0.0-1.0 |
| `recency` | `max(0.9, 1.0 - 0.001 × days_unused)`, never-used = 0.95 | 0.9-1.0 |

**Effectiveness modulates relevance, not competes with it.** A proven insight (eff=1.0) gets full relevance; a neutral insight (eff=0.5) gets 75%; a bad insight (eff=0.0) still gets 50%—it is demoted, not hidden.

**Minimum relevance gate:** `MIN_RELEVANCE_DEFAULT = 0.35`. Arctic-embed-m-v1.5 produces 0.05-0.25 for unrelated content, 0.35+ for related content. Below the gate, insights are excluded regardless of effectiveness.

### Feedback System

**EMA update (causal insights):**
```
new_eff = old_eff × (1 - FEEDBACK_EMA_WEIGHT) + outcome_value × FEEDBACK_EMA_WEIGHT
        = old_eff × 0.8 + outcome_value × 0.2
```

| Outcome | `outcome_value` |
|---------|-----------------|
| `delivered` | 1.0 |
| `plan_complete` | 1.0 |
| `blocked` | 0.0 |
| `crashed` | mapped to `blocked` (0.0) |

**Asymmetric erosion (non-causal insights):**
```
if eff > 0.5:
    new_eff = eff + (0.5 - eff) × EROSION_RATE    # 10% toward neutral
else:
    new_eff = eff                                    # bad insights stay bad
```

Non-causal erosion does NOT increment `use_count`, preventing double penalty with the read-time causal adjustment.

**Read-time causal adjustment:**
```
if use_count >= CAUSAL_MIN_USES (3):
    adjusted_eff = eff × max(CAUSAL_ADJUSTMENT_FLOOR, causal_hits / use_count)
```

Example: raw eff=0.50, use_count=20, causal_hits=0 → adjusted eff = 0.50 × 0.3 = 0.15 → falls below prune threshold.

### Semantic Deduplication

On `store()`, the new content is embedded and compared against all existing embeddings via vectorized matmul. If max similarity ≥ `DUPLICATE_THRESHOLD` (0.85):

- **Merge with upgrade:** If new content is longer OR existing effectiveness < 0.5, replaces content, embedding, and tags. Ensures higher-quality versions supersede originals.
- **Merge without upgrade:** Updates `last_used` only.
- Merge does NOT increment `use_count`. Re-encounter is not a "use".

### Decay

```python
decay(unused_days=30)
```

**Asymmetric:** Only decays insights with `effectiveness > 0.5` and `use_count > 0`. Formula:
```
new_eff = eff × 0.9 + 0.5 × 0.1    # 10% toward neutral
```

Bad insights (below 0.5) do not drift upward without positive causal evidence.

### Pruning

```python
prune(min_effectiveness=0.25, min_uses=3)
```

Three cleanup passes:

| Pass | Condition | Purpose |
|------|-----------|---------|
| **Performance** | Causal-adjusted eff < 0.25, use_count ≥ 3 | Remove proven-bad insights |
| **Orphan** | NULL embedding, use_count=0, >7 days old | Remove failed stores |
| **Ghost** | Valid embedding, use_count=0, >60 days old | Prevent unbounded accumulation |

Prune uses `_causal_adjusted_effectiveness()` — raw 0.50 with zero causal hits adjusts to 0.15 and falls below the threshold.

### Derived Insights

When a builder reports BLOCKED or PARTIAL without an explicit `INSIGHT:` marker, the extraction system derives a prescriptive insight:

```
"When {task}, be aware that {reason} can block progress"
```

Derived insights carry:
- `tags: ["derived", "failure"]`
- `derived: True` flag
- `initial_effectiveness: 0.35` (below neutral)

They must accumulate positive causal feedback to rise above the baseline. DELIVERED outcomes do NOT generate derived insights.

## Embedding System

**File:** `lib/memory/embeddings.py`

| Property | Value |
|----------|-------|
| Model | `Snowflake/snowflake-arctic-embed-m-v1.5` |
| Dimensions | 256 (Matryoshka truncation from 768, 98.4% quality retention) |
| Normalization | L2-normalized (dot product = cosine similarity) |
| Encoding | Asymmetric: `prompt_name="query"` for queries, plain for documents |
| Cache | `@lru_cache(maxsize=2000)` on `_embed_cached(text, is_query)` |
| Max text | 2000 characters (truncated before cache lookup) |
| Storage | Raw float32 BLOBs, 1024 bytes per embedding |

**Vectorized similarity:** `build_embedding_matrix()` joins all BLOBs into an `(N, 256)` float32 matrix. `mat @ q_vec` computes all N similarities in one operation. Used in both `store()` (dedup) and `recall()` (ranking).

**Background warmup:** `embeddings.py warmup` pre-loads the model into OS page cache during SessionStart (background process). By the time the orchestrator needs embeddings, the model files are already in memory.

## Injection System

**File:** `lib/injection.py`

### Core Functions

```python
inject_context(objective, limit=5, min_relevance=None, diversify=True)
    # → {"insights": ["[75%] When X...", ...], "names": [...], "total_insights": int}

format_prompt(task_id, task, objective, verify, insights, injected_names,
              warning="", parent_deliveries="", relevant_files=None, total_insights=0)
    # → Structured builder prompt string

batch_inject(tasks, limit=5)
    # → {"results": [{insights, names}, ...], "total_unique": int}

format_insights(memories)
    # → (lines: ["[75%] content", ...], names: ["insight-name", ...])

reset_session_tracking()
    # Clears _session_injected set
```

### Diversity Mechanisms

**In-process (orchestrator):** `_session_injected` module-level set. `batch_inject()` calls `inject_context()` sequentially with `diversify=True`; each call adds its names to the set, and subsequent calls suppress those names via `recall(suppress_names=...)`.

**Cross-process (hooks):** `inject_memory.py` reads existing `.helix/injected/*.json` sideband files from sibling agents to collect already-injected names. Earlier-spawned parallel builders write sideband files before later ones' SubagentStart hooks fire.

### Confidence Indicators

Builders see causal-adjusted effectiveness scores on injected insights:

```
INSIGHTS (from past experience):
  - [75%] When adding middleware, check for circular imports first
  - [50%] Database connections should use pooling for high-traffic endpoints

INJECTED: ["when-adding-middleware-check-for-circular", "database-connections-should-use-pooling"]
```

`[75%]` means 75% causal-adjusted effectiveness. `[50%]` is neutral—no feedback yet. The `INJECTED` line enables feedback attribution in SubagentStop.

### Cold-Start Signals

| Signal | Condition | Meaning |
|--------|-----------|---------|
| `NO_PRIOR_MEMORY: Novel domain.` | `count() == 0` | Zero insights in database |
| `NO_MATCHING_INSIGHTS: No matching insights found for this task.` | Insights exist, none matched | Semantically different; agent knows the system is functional |

## Extraction System

**File:** `lib/extraction.py`

### Single-Pass Architecture

`process_completion(transcript)` uses three pre-compiled regexes in a single pass:

```python
_OUTCOME_RE = re.compile(r'(DELIVERED|BLOCKED|PARTIAL|PLAN_COMPLETE|REMAINING):\s*(.+)', re.IGNORECASE)
_TASK_RE = re.compile(r'(?:TASK|OBJECTIVE):\s*(.+)', re.IGNORECASE)
_INJECTED_RE = re.compile(r'INJECTED:\s*(\[[^\]]*\])', re.IGNORECASE)
```

Returns:
```python
{
    "insight": {"content": str, "tags": list, "derived": bool} | None,
    "outcome": "delivered"|"blocked"|"partial"|"plan_complete"|"unknown",
    "injected": ["name1", "name2"],
    "summary_parts": [...],
    "task_parts": [...]
}
```

**Last-match-wins** for outcomes: injected context at the top of the transcript may contain DELIVERED/BLOCKED markers from parent deliveries. The agent's own outcome at the end takes precedence.

**Insight extraction priority:**
1. Explicit: `INSIGHT: {"content": "...", "tags": [...]}`
2. Derived from BLOCKED/PARTIAL with task context (at `initial_effectiveness=0.35`)
3. No insight (DELIVERED without explicit INSIGHT marker)

## Causal Feedback Loop

**File:** `lib/hooks/extract_learning.py:filter_causal_insights()`

The bridge between "insight was present" and "insight was causally relevant":

1. **Resolve context embedding:** From sideband (cached, zero-cost) or recompute via `embed()`
2. **Batch-fetch insight embeddings:** Single `SELECT name, embedding FROM insight WHERE name IN (...)`
3. **Vectorized similarity:** `build_embedding_matrix(blobs)` → `mat @ ctx_vec`
4. **Threshold gate:** Cosine similarity ≥ `CAUSAL_SIMILARITY_THRESHOLD` (0.50)
5. **Result:** Subset of injected names that are causally relevant

**Conservative design — four paths return `[]`:**
- Empty names or empty task context
- Embedding computation failure
- General exception
- No names pass the threshold (natural result)

No feedback is better than wrong feedback. The system protects itself from incorrect attribution at every opportunity.

## Build Loop

**File:** `lib/build_loop.py`

7 CLI subcommands for DAG-based wave execution:

| Subcommand | Purpose |
|------------|---------|
| `wait-for-explorers` | Poll `.helix/explorer-results/` until expected count |
| `wait-for-builders` | Poll `.helix/task-status.jsonl` until all task IDs resolved |
| `parent-deliveries` | Map next-wave tasks to formatted delivery summaries |
| `detect-cycles` | DFS cycle detection in dependency graph |
| `check-stalled` | Detect build impasse (pending tasks, none ready) |
| `get-ready` | Identify unblocked tasks ready for execution |
| `status` | Combined get-ready + check-stalled in one call |

### Task Readiness

`get_ready_tasks()` uses `delivered_ids` only. A task is ready when ALL entries in its `blockedBy` list are in the delivered set. Blocked or unknown-outcome blockers do NOT unblock downstream tasks.

### Stall Recovery

The orchestrator detects stalls via `build_status()` (`pending_count > 0` but `ready_count == 0`). Before choosing a strategy, it recalls insights about the blocked area (`core.py recall "{blocked_task_description}" --limit 3`) to check for known stall patterns. Then chooses:
- Skip single obvious blockers
- Re-plan blocked subtrees (informed by recalled constraints)
- Abort after 3+ attempts on the same blocker

### PARTIAL Handling

PARTIAL outcomes fold the REMAINING work into a new task in the next wave, rather than re-dispatching the entire original task.

## Configuration

| Variable | Purpose | Default |
|----------|---------|---------|
| `HELIX_DB_PATH` | Custom database location | `.helix/helix.db` |
| `HELIX_PLUGIN_ROOT` | Plugin root path | Read from `.helix/plugin_root` |
| `HELIX_PROJECT_DIR` | Project root for hooks | Current working directory |
| `HELIX_ROOT` | Plugin root (set by setup-env.sh) | Same as plugin root |

### settings.json Permissions

Helix hooks require these permissions in `~/.claude/settings.json`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python3 *lib/hooks/inject_memory.py*)",
      "Bash(python3 *lib/hooks/extract_learning.py*)",
      "Bash(python3 *lib/hooks/session_end.py*)",
      "Bash(*setup-env.sh*)"
    ]
  }
}
```

## Tuning Constants

All named constants in `lib/memory/core.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `DUPLICATE_THRESHOLD` | 0.85 | Cosine similarity for semantic dedup |
| `MIN_RELEVANCE_DEFAULT` | 0.35 | Minimum cosine similarity for recall results |
| `CAUSAL_SIMILARITY_THRESHOLD` | 0.50 | Gate for causal feedback attribution |
| `FEEDBACK_EMA_WEIGHT` | 0.2 | EMA learning rate (~3 outcomes to move 0.5→0.6) |
| `DECAY_RATE` | 0.1 | Rate dormant insights drift toward neutral |
| `EROSION_RATE` | 0.10 | Rate non-causal insights drift toward neutral |
| `CAUSAL_ADJUSTMENT_FLOOR` | 0.3 | Minimum multiplier for causal hit ratio |
| `CAUSAL_MIN_USES` | 3 | Uses before causal adjustment activates |
| `RECENCY_DECAY_PER_DAY` | 0.001 | 0.1% score penalty per day unused |
| `RECENCY_FLOOR` | 0.9 | Floor for recency multiplier |

Embedding constants in `lib/memory/embeddings.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `EMBED_DIM` | 256 | Matryoshka truncation from 768 |
| `MAX_TEXT_CHARS` | 2000 | Max text length before truncation |

## CLI Reference

### Memory Operations

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store insight
python3 "$HELIX/lib/memory/core.py" store \
  --content "When X, do Y because Z" --tags '["pattern"]'

# Recall by semantic similarity
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5

# Get single insight
python3 "$HELIX/lib/memory/core.py" get "insight-name"

# Apply feedback with causal filtering
python3 "$HELIX/lib/memory/core.py" feedback \
  --names '["insight-1"]' --outcome delivered --causal-names '["insight-1"]'

# Decay dormant insights
python3 "$HELIX/lib/memory/core.py" decay --days 30

# Prune low performers
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Health check
python3 "$HELIX/lib/memory/core.py" health
```

### DAG Operations

```bash
# Combined readiness + stall check
python3 "$HELIX/lib/build_loop.py" status --tasks '[...]'

# Detect cycles
python3 "$HELIX/lib/build_loop.py" detect-cycles --dependencies '{"task-002": ["task-001"]}'

# Check for stalled build
python3 "$HELIX/lib/build_loop.py" check-stalled --tasks '[...]'

# Get ready tasks
python3 "$HELIX/lib/build_loop.py" get-ready --tasks '[...]'

# Wait for builder results
python3 "$HELIX/lib/build_loop.py" wait-for-builders --task-ids "task-001,task-002"

# Wait for explorer results
python3 "$HELIX/lib/build_loop.py" wait-for-explorers --count 3

# Collect parent deliveries
python3 "$HELIX/lib/build_loop.py" parent-deliveries --results '...' --blockers '...'
```

### Injection Operations

```bash
# Batch inject for a wave
python3 "$HELIX/lib/injection.py" batch-inject --tasks '["obj1", "obj2"]' --limit 5

# Single injection
python3 "$HELIX/lib/injection.py" inject --objective "query text" --limit 5
```

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: explore → recall → plan → build → learn → complete |
| `/helix-query <text>` | Search insights by meaning (top 10 results) |
| `/helix-stats` | Memory health metrics |

## File Structure

```
helix/
├── .claude-plugin/
│   └── plugin.json           # Plugin manifest
├── hooks/
│   └── hooks.json            # Hook configuration (4 hooks)
├── agents/
│   ├── explorer.md           # Parallel reconnaissance (sonnet)
│   ├── planner.md            # Task decomposition (opus)
│   └── builder.md            # Task execution (opus)
├── lib/
│   ├── __init__.py           # Version: 2.0.0
│   ├── paths.py              # .helix/ directory resolution
│   ├── log.py                # Shared log_error() for hooks
│   ├── hooks/
│   │   ├── __init__.py
│   │   ├── inject_memory.py  # SubagentStart: injection + sideband
│   │   ├── extract_learning.py # SubagentStop: extraction + feedback
│   │   └── session_end.py    # SessionEnd: decay + prune + cleanup
│   ├── memory/
│   │   ├── __init__.py       # Exports 8 primitives
│   │   ├── core.py           # store, recall, get, feedback, decay, prune, count, health
│   │   └── embeddings.py     # snowflake-arctic-embed-m-v1.5 (256-dim)
│   ├── db/
│   │   ├── __init__.py       # Exports get_db, write_lock, init_db
│   │   └── connection.py     # SQLite singleton, WAL, migrations v1-v10
│   ├── injection.py          # inject_context, format_prompt, batch_inject
│   ├── extraction.py         # process_completion, extract_insight, extract_outcome
│   └── build_loop.py         # DAG ops: cycles, readiness, stall, wait, status
├── scripts/
│   └── setup-env.sh          # SessionStart: venv + env + warmup
├── skills/
│   ├── helix/
│   │   └── SKILL.md          # Main orchestrator
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
├── tests/
│   ├── conftest.py           # Fixtures: test_db, mock_embeddings, isolated_env
│   ├── test_memory_core.py   # 40 tests — 8 primitives
│   ├── test_injection.py     # 17 tests — inject_context, format_prompt, batch_inject
│   ├── test_extraction.py    # 36 tests — process_completion, last-match-wins
│   ├── test_inject_memory.py # 27 tests — SubagentStart hook
│   ├── test_extract_learning.py # 21 tests — SubagentStop hook
│   ├── test_extract_causal.py # 11 tests — causal filtering (real embeddings)
│   ├── test_build_loop.py    # 27 tests — DAG ops, wave management
│   ├── test_causal_feedback.py # 9 tests — dual-path feedback (real embeddings)
│   ├── test_relevance_gate.py # 5 tests — min_relevance filtering (real embeddings)
│   └── test_session_end.py   # 4 tests — SessionEnd hook
└── .helix/                   # Runtime (created on first use)
    ├── helix.db              # SQLite database (WAL mode)
    ├── plugin_root           # Plugin path for sub-agents
    ├── session.log           # Session event log
    ├── extraction.log        # Injection + extraction diagnostics
    ├── injected/             # Sideband files (consume-once per agent)
    ├── explorer-results/     # Explorer findings by agent_id
    └── task-status.jsonl     # Builder outcomes (JSONL, append-only)
```

## What Helix Is Not

- A production autonomous agent system (no SLA guarantees)
- A multi-user collaboration tool (single-user, local SQLite)
- A model-agnostic framework (Claude-only by design)
- A GUI-based tool (CLI power users only)
