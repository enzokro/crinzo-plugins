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
│  memory/edges.py    - Graph edge helpers (similar, led_to)  │
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
│  insight_edges table: similar + led_to graph relationships │
└─────────────────────────────────────────────────────────────┘
```

**Key principle**: Hooks separate judgment from mechanics. Memory injection, learning extraction, and feedback attribution happen automatically. The orchestrator retains judgment: what to store, when to override feedback, what candidates to keep.

## Orchestrator Phases

Defined in `skills/helix/SKILL.md`. Six phases:

```
RECALL → EXPLORE → PLAN → BUILD (loop) → LEARN → COMPLETE
```

| Phase | Agent | Purpose |
|-------|-------|---------|
| **RECALL** | Orchestrator (no agent) | `strategic-recall` (graph_hops=1) → CONSTRAINTS + RISK_AREAS + EXPLORATION_TARGETS |
| **EXPLORE** | Explorer swarm (sonnet, parallel) | Map codebase structure, scope informed by recalled insights |
| **PLAN** | Planner (opus) | Decompose objective into task DAG, respecting CONSTRAINTS |
| **BUILD** | Builder swarm (opus, parallel waves) | Execute tasks; stall recovery uses recall too |
| **LEARN** | Orchestrator + user | Observe patterns, ask user, store validated insights |
| **COMPLETE** | Orchestrator | Summarize deliveries, blocks, stored insights |

**RECALL** is the orchestrator's strategic memory layer. Before exploration, the orchestrator calls `injection.py strategic-recall` with the objective—a broader sweep (limit=15, min_relevance=0.30) than tactical recall (limit=3, min_relevance=0.35). Both use the default `graph_hops=1`, expanding results through `similar` and `led_to` edges to surface related insights beyond direct vector/keyword matches. The returned JSON includes full insight metadata (tags, effectiveness, causal stats), graph hop markers (`_hop: 0` or `1`), and pre-computed summary statistics (coverage ratio, proven/risky/untested counts, tag distribution, `graph_expanded_count`). The orchestrator synthesizes insights into three blocks:
- **CONSTRAINTS** — from proven insights (effectiveness >= 0.70): decomposition rules, verification requirements, sequencing
- **RISK_AREAS** — from risky insights (effectiveness < 0.40) or `derived`/`failure` tags: areas needing extra verification, smaller tasks
- **EXPLORATION_TARGETS** — areas referenced by insight content/tags that expand exploration scope beyond the naive objective

Coverage signal: `coverage_ratio > 0.3` = well-mapped, trust constraints; `< 0.1` = uncharted, expand exploration. On cold start (no insights), all blocks omitted; no degradation. Skipped on fast path (single-file changes).

**Two-level memory injection** (both use `graph_hops=1` by default):
- **Strategic (RECALL phase):** Orchestrator → `CONSTRAINTS` + `RISK_AREAS` → planner prompt + `EXPLORATION_TARGETS` → explorer scope. Broader sweep (limit=15, min_relevance=0.30). Informs *how to decompose* and *where to look*.
- **Tactical (SubagentStart hook):** Hook → `INSIGHTS` → builder/planner prompt. Narrower focus (limit=3, min_relevance=0.35). Informs *how to execute*.

## Agents

Three agents with distinct roles:

| Agent | Model | Purpose | Tools | Hook Injection |
|-------|-------|---------|-------|----------------|
| **Explorer** | Sonnet | Parallel reconnaissance | Read, Grep, Glob, Bash | None (no SubagentStart) |
| **Planner** | Opus | Task decomposition | Read, Grep, Glob, Bash | SubagentStart: insights |
| **Builder** | Opus | Task execution | Read, Write, Edit, Grep, Glob, Bash | SubagentStart: insights + sideband |

### Explorer (`agents/explorer.md`)

Explores ONE scope of a codebase partition as part of a parallel swarm. Follows a 5-step procedure; returns structured JSON findings with line-level precision.

Input:
- `CONTEXT` (optional): Recalled insights about this area — known coupling, risk modules, patterns. Prioritizes tracing referenced areas during exploration.
- `SCOPE`: Directory path or partition
- `FOCUS`: What to find within scope
- `OBJECTIVE`: User goal for context

Procedure:
1. **Context check** — read CONTEXT if provided; prioritize insight-referenced areas
2. **Orient** — glob for entry points (index files, `__init__.py`, main.*, config)
3. **Map interfaces** — grep for exports, public functions, class definitions, route handlers with line numbers
4. **Trace dependencies** — grep for imports and cross-references to other partitions
5. **Sample implementations** — read 1-2 core files for patterns (don't read every file)
6. **Locate tests** — glob for test files, note paths without reading

Stops after entry points, key interfaces with line numbers, and cross-scope dependencies are mapped (~15-20 file reads).

Output (JSON):
```json
{
  "scope": "src/api/",
  "focus": "route handlers",
  "status": "success",
  "findings": [
    {"file": "src/auth.py", "what": "verify_token():42 — JWT validation, called by middleware.py:check_auth()"},
    {"file": "src/auth.py", "what": "create_token():78 — signs payload with config.SECRET_KEY, returns str"},
    {"file": "src/models/user.py", "what": "User:15 — SQLAlchemy model, FK to roles; tests at tests/test_user.py"}
  ]
}
```

Each finding requires: exact relative path, function/class name + line number + one-sentence purpose + connections.

Explorer results written to `.helix/explorer-results/{agent_id}.json` by SubagentStop hook.

### Planner (`agents/planner.md`)

Decomposes objective into task DAG using Claude Code's native Task system. Structured sections for task-sizing, dependency validation, verification patterns, and anti-pattern avoidance.

Input:
- `OBJECTIVE`: What to build
- `EXPLORATION`: Merged explorer findings
- `CONSTRAINTS` (optional): Strategic constraints from orchestrator's RECALL phase—decomposition patterns, verification requirements, risk areas, sequencing hints from past sessions. Respected unless they directly conflict with the current objective.

Task-sizing rules:
- **Target**: 1-3 files per task; a builder should finish in one focused session
- **Split**: when task mixes unrelated concerns or touches >5 files
- **Merge**: when two changes in the same file are interdependent
- **Test tasks**: parallel per implementation task, each blocked only by its impl

Dependency rules:
- Only `blocked_by` when task B reads/imports files task A creates or modifies
- Conceptual relatedness is NOT a dependency; "makes sense to do first" is NOT a dependency
- When uncertain, prefer parallel — false dependencies serialize the build loop

Verification patterns (concrete commands per task type):

| Task type | Verify pattern |
|-----------|----------------|
| New module | `python -c "from mod import X"` |
| API endpoint | `pytest tests/test_api.py -k test_endpoint_name` |
| Refactor | `pytest tests/test_module.py` (full module suite) |
| Config/schema | `python -c "import json; json.load(open('config.json'))"` |
| Type changes | `tsc --noEmit` or `mypy src/module.py` |

Anti-patterns to avoid:
1. "Setup environment" tasks that produce no artifacts consumed by others
2. Serial test bottleneck — one test task blocked_by all impl tasks
3. "Finalize" or "cleanup" tasks — vague scope leads to BLOCKED
4. Conceptual dependencies — ordering based on intuition, not data flow

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

Or error: `ERROR: {description}`

### Builder (`agents/builder.md`)

Executes a single task through structured phases. Reports DELIVERED, BLOCKED, or PARTIAL.

Input (structured fields):
- Required: `TASK_ID`, `TASK`, `OBJECTIVE`, `VERIFY`
- Optional: `RELEVANT_FILES`, `PARENT_DELIVERIES`, `WARNING`, `INSIGHTS`
- `INJECTED`: List of insight names for feedback tracking

Execution phases:

1. **Pre-flight** — address WARNING if present; review PARENT_DELIVERIES; read RELEVANT_FILES (if a file listed for modification doesn't exist and task says "modify"/"update" → BLOCKED, don't create it); check INSIGHTS.
2. **Implement** — understand interfaces/invariants before changing; minimal change; preserve existing patterns unless task requires changing them.
3. **Verify** — run VERIFY command exactly as specified. Pass → DELIVERED. Fail → failure diagnosis.
4. **Failure diagnosis** — read full error output; categorize (import error | type error | assertion failure | runtime crash | timeout); trace to root cause; fix and re-run VERIFY. Second failure with different error → BLOCKED (cascading). Second failure with same error → BLOCKED (fix didn't address root cause).

Output:
```
DELIVERED: <summary in 100 chars>
```
Or:
```
PARTIAL: <what was completed>
REMAINING: <what blocked>
```
Or:
```
BLOCKED: <reason with error details>
```

Optional on any outcome:
```
INSIGHT: {"content": "When X, do Y because Z", "tags": ["pattern"]}
```

Insight quality test: would this change a future builder's approach? "I had to install X" is not useful. "When modifying Y, Z breaks because of hidden coupling via shared config" is.

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
    │  Phase 3d: provenance edges (led_to from causal parents → child) — independent
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
2. Recalls up to 3 insights with `suppress_names` to avoid repeating what siblings received
3. Writes sideband file with insight names, objective, and base64-encoded query embedding
4. Returns `{"additionalContext": "INSIGHTS (from past experience):\n  - [75%] When X..."}`

Cold-start signals:
- `NO_PRIOR_MEMORY: Novel domain.` — zero insights in database
- `NO_MATCHING_INSIGHTS: No matching insights found for this task.` — insights exist but none relevant

### SubagentStop Hook

**File:** `lib/hooks/extract_learning.py`

Fires for all helix agents. Multi-phase pipeline where each phase has independent error boundaries:

**Phase 1 — Handoff:** Writes `.helix/task-status.jsonl` (append-only JSONL) and `.helix/explorer-results/{agent_id}.json`. These files are consumed by `build_loop.py` and must succeed even if insight processing fails.

**Phase 2 — Outcome:** Runs `process_completion()` for single-pass extraction. For unknown outcomes with `has_error`, maps to "crashed". Otherwise retries with exponential backoff (0.15s, 0.35s, 0.75s) to handle transcript write race conditions.

**Phase 3 — Learning (four independent boundaries):**
- **3a:** Store extracted insight (`initial_effectiveness=0.35` for derived insights). Returns stored insight name for provenance linking.
- **3b:** Read sideband → merge injected names → resolve task context (prefers sideband objective) → causal filter → apply feedback (crashed → blocked mapping)
- **3c:** Log extraction result with causal ratio
- **3d:** Create provenance edges — if a new insight was stored (3a) and causal parent names exist, `_create_provenance_edges()` looks up IDs by name and calls `add_edges()` with `relation='led_to'`, `weight=1.0`. Traces how existing insights spawned new knowledge.

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
    embedding BLOB,                    -- 768-dim snowflake-arctic-embed-m-v1.5, f32
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

```sql
CREATE VIRTUAL TABLE insight_fts USING fts5(
    content, tags,
    content=insight, content_rowid=id
);

-- Auto-sync triggers: INSERT, DELETE, UPDATE OF content/tags
```

```sql
CREATE TABLE insight_edges (
    src_id INTEGER NOT NULL,
    dst_id INTEGER NOT NULL,
    weight REAL NOT NULL,
    relation TEXT NOT NULL,          -- 'similar' or 'led_to'
    created_at TEXT NOT NULL,
    PRIMARY KEY (src_id, dst_id, relation)
);
```

Two relation types:
- **`similar`** — undirected. Canonical ordering `(min, max)` ensures `(A,B)` and `(B,A)` map to the same row. Auto-created by `store()` when `RELATED_THRESHOLD (0.60) ≤ sim < DUPLICATE_THRESHOLD (0.85)`. Top `MAX_AUTOLINK_EDGES (5)` per insert. Reuses the dedup similarity vector — zero extra DB queries.
- **`led_to`** — directional (parent → child). Created by `extract_learning` Phase 3d when causal parent insights spawn a derived child. Weight 1.0.

No FK pragma — orphaned edges cleaned manually by `prune()` and `delete_edges_for()`.

**Schema version:** v12. Migrations in `lib/db/connection.py` as a data-driven `_MIGRATIONS` list — each migration is a `(version, sql)` tuple processed by a generic loop. Notable: v8 NULLed all embeddings (model migration), v9 dropped legacy tables, v10 dropped redundant `idx_insight_name`, v11 adds FTS5 table (`insight_fts`) with 3 auto-sync triggers for hybrid search, v12 adds `insight_edges` table for graph relationships.

### 8 Primitives (`lib/memory/core.py`)

```python
store(content, tags=None, initial_effectiveness=0.5)
    # → {"status": "added"|"merged"|"rejected", "name": str, "reason": str}
    # Auto-links to semantically related insights as 'similar' edges (best-effort)

recall(query, limit=5, min_effectiveness=0.0, min_relevance=0.35,
       suppress_names=None, graph_hops=1)
    # → [insights with _relevance, _effectiveness, _score, _hop]
    # _hop: 0 (direct) or 1 (graph-expanded via similar/led_to edges)
    # graph_hops=1 by default; pass 0 to disable graph expansion

get(name)
    # → single insight dict with parsed tags, or None

feedback(names, outcome, causal_names=None)
    # → {"updated": int, "outcome": str, "causal": int, "eroded": int}

decay(unused_days=30)
    # → {"decayed": int, "threshold_days": int}

prune(min_effectiveness=0.25, min_uses=3)
    # → {"pruned": int, "orphans_cleaned": int, "ghosts_cleaned": int, "remaining": int}
    # Also cleans orphaned edges for deleted insights

count()
    # → int (total insight count, no numpy import)

health()
    # → {"status": str, "total_insights": int, "total_edges": int,
    #    "connected_ratio": float, "avg_edges_per_insight": float,
    #    "loop_coverage": float,   # fraction of insights with use_count > 0
    #    "by_tag": dict, "effectiveness": dict, ...}
```

**Graph helpers** (`lib/memory/edges.py`):
```python
add_edges(edges: List[Tuple[src_id, dst_id, weight, relation]])
    # INSERT OR IGNORE; canonical (min,max) ordering for 'similar'; no self-loops

get_neighbors(insight_ids, relation=None, limit=10)
    # Bidirectional JOIN → full insight rows with edge_weight, edge_relation

delete_edges_for(insight_ids)
    # Manual CASCADE: deletes edges where src_id OR dst_id in set
```

**Performance note:** `numpy` is imported locally only in `store()` and `recall()`. Lightweight operations (`count`, `decay`, `feedback`, `prune`, `health`, `get`) avoid the ~100-200ms numpy import tax. Graph auto-linking in `store()` reuses the dedup similarity vector — zero extra DB queries or embeddings.

### Scoring Formula (Hybrid Retrieval with RRF)

Recall uses hybrid retrieval: vector similarity and FTS5 keyword search, fused via Reciprocal Rank Fusion (RRF).

```
1. Vector ranking:  embed(query) → dot product against all insight embeddings → rank by cosine sim
2. Keyword ranking: FTS5 MATCH on insight content + tags → rank by BM25
3. RRF fusion:      rrf_score = 1/(K + vec_rank) + 1/(K + fts_rank)    [K=60]
4. Final score:     rrf_score × (0.5 + 0.5 × effectiveness) × recency
```

| Component | Source | Range |
|-----------|--------|-------|
| `rrf_score` | Reciprocal Rank Fusion of vector + FTS5 rankings | 0.0-~0.033 |
| `effectiveness` | Causal-adjusted: `eff × max(0.33, causal_hits/use_count)` for ≥3 uses | 0.0-1.0 |
| `recency` | `max(0.85, 1.0 - 0.003 × days_unused)`, never-used = 0.95 | 0.85-1.0 |

**Why hybrid?** Vector similarity captures semantic meaning but can underweight exact technical terms (error codes, library names, CLI flags). FTS5 keyword matching surfaces these precisely. RRF combines both rankings without requiring score normalization—an insight that ranks high in both lists gets a strong boost; one that ranks high in only one still surfaces.

**Graceful degradation:** If FTS5 is unavailable (missing table, error), recall falls back to pure vector ranking. The `min_relevance` cosine gate (`MIN_RELEVANCE_DEFAULT = 0.35`) applies to all candidates—FTS cannot bypass it.

**FTS5 query sanitization:** Natural-language queries are tokenized, stripped of non-alphanumeric characters (hyphens preserved), FTS5 reserved words (`AND`, `OR`, `NOT`, `NEAR`) removed, and remaining tokens quoted and joined with `OR`.

**Effectiveness modulates RRF score, not competes with it.** A proven insight (eff=1.0) gets full score; a neutral insight (eff=0.5) gets 75%; a bad insight (eff=0.0) still gets 50%—it is demoted, not hidden.

**FTS5 sync:** The `insight_fts` table uses external content mode (no data duplication). Three triggers auto-sync on INSERT, DELETE, and UPDATE OF content/tags. Feedback-only updates (effectiveness, use_count) do not fire triggers.

### Graph Expansion

When `graph_hops >= 1`, recall expands top direct results via the insight graph:

1. Collect IDs of top-scoring direct results
2. `get_neighbors(top_ids)` — single bidirectional JOIN on `insight_edges`
3. For each neighbor not already in results and not in `suppress_names`:
   - Compute vector similarity to query (`q_vec @ nbr_vec`)
   - Apply `min_relevance` gate
   - Score: `vector_sim × HOP_DISCOUNT (0.7) × (0.5 + 0.5 × eff) × recency`
4. Merge into results, re-sort, trim to `limit`

Graph-expanded results carry `_hop: 1`; direct results carry `_hop: 0`. Graph expansion is best-effort — exceptions are logged to stderr and fall back to direct results only.

**Default on all paths:** `recall()` defaults to `graph_hops=1`. All callers—`strategic_recall()`, `inject_context()`, the SubagentStart hook, and the CLI—benefit from graph expansion automatically. Pass `graph_hops=0` to disable.

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
    new_eff = eff + (0.5 - eff) × EROSION_RATE    # 9% toward neutral
else:
    new_eff = eff                                    # bad insights stay bad
```

Non-causal erosion does NOT increment `use_count`, preventing double penalty with the read-time causal adjustment.

**Read-time causal adjustment:**
```
if use_count >= CAUSAL_MIN_USES (3):
    adjusted_eff = eff × max(CAUSAL_ADJUSTMENT_FLOOR, causal_hits / use_count)
```

Example: raw eff=0.50, use_count=20, causal_hits=0 → adjusted eff = 0.50 × 0.33 = 0.165 → falls below prune threshold.

### Semantic Deduplication

On `store()`, the new content is embedded and compared against all existing embeddings via vectorized matmul. If max similarity ≥ `DUPLICATE_THRESHOLD` (0.85):

- **Merge with upgrade:** If new content is longer OR existing effectiveness < 0.5, replaces content, embedding, and tags. Ensures higher-quality versions supersede originals.
- **Merge without upgrade:** Updates `last_used` only.
- Merge does NOT increment `use_count`. Re-encounter is not a "use".

**User-provided insights skip dedup entirely.** When `tags` includes `"user-provided"` (set by the LEARN phase for user-confirmed insights), the dedup check is bypassed. Human corrections always get their own row, even if semantically similar to an existing insight. Auto-linking still fires (0.60-0.85 range), creating `similar` edges that connect the user's version to the existing one. The causal feedback loop then evaluates both independently—if the user's correction is better, it accumulates positive feedback; if the existing version was already correct, the user's version erodes naturally.

### Decay

```python
decay(unused_days=30)
```

**Asymmetric:** Only decays insights with `effectiveness > 0.5` and `use_count > 0`. Formula:
```
new_eff = eff × 0.9 + 0.5 × 0.1    # DECAY_RATE toward neutral
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

Prune uses `_causal_adjusted_effectiveness()` — raw 0.50 with zero causal hits adjusts to 0.165 and falls below the threshold.

**Edge cleanup:** After deleting insights, prune calls `delete_edges_for()` to remove all edges referencing the deleted IDs. Runs in the same `write_lock` block as the insight deletion.

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
| Dimensions | 768 (full model output, L2-normalized) |
| Normalization | L2-normalized (dot product = cosine similarity) |
| Encoding | Asymmetric: `prompt_name="query"` for queries, plain for documents |
| Cache | `@lru_cache(maxsize=2000)` on `_embed_cached(text, is_query)` |
| Max text | 2000 characters (truncated before cache lookup) |
| Storage | Raw float32 BLOBs, 3072 bytes per embedding |

**Vectorized similarity:** `build_embedding_matrix()` joins all BLOBs into an `(N, 768)` float32 matrix. `mat @ q_vec` computes all N similarities in one operation. Used in `store()` (dedup), `recall()` (vector ranking for RRF), and causal filtering.

**Background warmup:** `embeddings.py warmup` pre-loads the model into OS page cache during SessionStart (background process). By the time the orchestrator needs embeddings, the model files are already in memory.

## Injection System

**File:** `lib/injection.py`

### Core Functions

```python
inject_context(objective, limit=3, min_relevance=None, diversify=True)
    # → {"insights": ["[75%] When X...", ...], "names": [...], "total_insights": int}

format_prompt(task_id, task, objective, verify, insights, injected_names,
              warning="", parent_deliveries="", relevant_files=None, total_insights=0)
    # → Structured builder prompt string

batch_inject(tasks, limit=3)
    # → {"results": [{insights, names}, ...], "total_unique": int}

strategic_recall(objective, limit=15, min_relevance=0.30)
    # → {"insights": [{name, content, effectiveness, use_count, causal_hits,
    #     tags, _relevance, _effectiveness, _score, _hop}, ...],
    #    "summary": {total_recalled, total_in_system, avg_relevance,
    #     avg_effectiveness, proven_count, risky_count, untested_count,
    #     tag_distribution, coverage_ratio, graph_expanded_count}}
    # Uses graph_hops=1 for broad sweep; _hop=1 entries are graph-expanded

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

All named constants in `lib/memory/core.py`. Each value has a principled basis; cross-referenced against reinforcement learning theory, prospect theory, cognitive science, spaced repetition research, and production IR systems.

| Constant | Value | Basis |
|----------|-------|-------|
| `RRF_K` | 60 | Cormack, Clarke & Buettcher (2009) SIGIR. Tested k=1-1000 across TREC benchmarks; k=60 most robust. Adopted by Elasticsearch, OpenSearch, Azure AI Search as default. |
| `FEEDBACK_EMA_WEIGHT` | 0.2 | Sutton & Barto (2018) Ch. 2: constant-alpha EMA for non-stationary bandits; 0.1-0.2 is the practical range. Effective window = `2/α - 1 = 9` feedback events. Appropriate for sparse feedback (few uses per project lifecycle). |
| `EROSION_RATE` | 0.09 | Loss-aversion calibrated. Kahneman & Tversky (1992): λ=2.25. Erosion (non-causal, weaker evidence) relates to EMA weight (causal, stronger evidence) via: `EMA_WEIGHT / λ ≈ 0.2 / 2.25 ≈ 0.089`. Baumeister et al. (2001): "bad is stronger than good" — non-causal erosion is intentionally weaker than causal learning. |
| `DECAY_RATE` | 0.1 | Per-session exponential: `new = eff × 0.9 + 0.5 × 0.1`. Anderson & Schooler (1991) power-law forgetting; per-session exponential produces similar shape with irregular spacing. Asymptotic to 0.5 (neutral). |
| `HOP_DISCOUNT` | 0.7 | PageRank damping d=0.85 (Brin & Page 1998) is the upper bound — link traversal preserves ~85% of authority. Collins & Loftus (1975) spreading activation: single-hop semantic neighbors retain substantial relevance. 0.7 balances signal preservation against noise; at 0.5 (previous), graph-expanded insights barely survived the min_relevance gate. |
| `RECENCY_DECAY_PER_DAY` | 0.003 | Collaborative filtering literature: 150-day half-life optimal for preference data (Ding & Li 2005, CIKM). At 0.003/day: 231-day half-life, conservative for semantic/procedural knowledge (longer-lived than episodic memory per Ebbinghaus 1885, confirmed by Murre & Dros 2015 R²=98.8%). |
| `RECENCY_FLOOR` | 0.85 | 15% maximum lifetime penalty. Floor reached at ~50 days. Creates three temporal tiers: fresh (0-15d, <5% penalty), aging (15-50d, 5-15%), dormant (50d+, capped at 15%). Ebbinghaus-inspired shape: rapid initial decay, then plateau. Protects evergreen strategic knowledge. |
| `CAUSAL_ADJUSTMENT_FLOOR` | 0.33 | At-chance base rate for `CAUSAL_MIN_USES=3`. With 0 causal hits out of 3 uses, the floor matches the probability of one hit by chance (1/3=0.333). Clean progression: 0/3→0.33, 1/3→0.33, 2/3→0.67, 3/3→1.0. |
| `CAUSAL_MIN_USES` | 3 | SM-2 ramp-up phase (Wozniak 1987). Minimum observations before the causal ratio is statistically meaningful. |
| `DUPLICATE_THRESHOLD` | 0.85 | Standard for embedding-based dedup; corresponds to paraphrase-level similarity on STS benchmarks with arctic-embed-m-v1.5. |
| `MIN_RELEVANCE_DEFAULT` | 0.35 | arctic-embed-m-v1.5 score distribution: unrelated 0.05-0.25, topically related 0.35+. Gate at the boundary. |
| `CAUSAL_SIMILARITY_THRESHOLD` | 0.50 | Attribution gate for feedback. Query-document similarity (asymmetric encoding) naturally produces lower scores than content-content. Top 20-30% of insight-query pairs pass at this threshold. Raised from 0.40 for tighter causal attribution. |
| `RELATED_THRESHOLD` | 0.60 | Boundary between "topically related" (0.35-0.60) and "semantically similar" (0.60-0.85) in arctic-embed-m-v1.5's characteristic score distribution. |
| `MAX_AUTOLINK_EDGES` | 5 | Small-world network theory (Watts & Strogatz 1998): average degree 4-8 produces short path lengths + high clustering. Dunbar (1992) innermost layer = 5 closest associates. At 100 insights, yields average degree ~10 (within small-world regime). |

### References

- Cormack, Clarke & Buettcher (2009). "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods." *SIGIR*.
- Sutton & Barto (2018). *Reinforcement Learning: An Introduction*, 2nd ed. Ch. 2.
- Kahneman & Tversky (1992). "Advances in Prospect Theory." *J. Risk and Uncertainty* 5(4). Loss aversion λ=2.25.
- Baumeister et al. (2001). "Bad is Stronger than Good." *Review of General Psychology* 5(4).
- Brin & Page (1998). "The Anatomy of a Large-Scale Hypertextual Web Search Engine." PageRank d=0.85.
- Collins & Loftus (1975). "A Spreading-Activation Theory of Semantic Processing." *Psychological Review* 82(6).
- Ebbinghaus (1885). *Uber das Gedachtnis*.
- Murre & Dros (2015). "Replication and Analysis of Ebbinghaus' Forgetting Curve." *PLOS ONE* 10(7).
- Anderson & Schooler (1991). "Reflections of the Environment in Memory." *Psychological Science* 2(6).
- Ding & Li (2005). "Time Weight Collaborative Filtering." *CIKM*. 150-day half-life.
- Watts & Strogatz (1998). "Collective dynamics of 'small-world' networks." *Nature* 393.
- Dunbar (1992). "Neocortex size as a constraint on group size in primates." *J. Human Evolution* 22(6).
- Wozniak (1987). SuperMemo SM-2 algorithm.

Strategic recall constants in `lib/injection.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `STRATEGIC_RECALL_LIMIT` | 15 | Default max insights for strategic recall (vs tactical 3) |
| `STRATEGIC_MIN_RELEVANCE` | 0.30 | Wider relevance gate (vs tactical 0.35) |
| `STRATEGIC_HIGH_EFFECTIVENESS` | 0.70 | Threshold for "proven" classification → CONSTRAINTS |
| `STRATEGIC_LOW_EFFECTIVENESS` | 0.40 | Threshold for "risky" classification → RISK_AREAS |

Embedding constants in `lib/memory/embeddings.py`:

| Constant | Value | Purpose |
|----------|-------|---------|
| `EMBED_DIM` | 768 | Full model output dimension |
| `MAX_TEXT_CHARS` | 2000 | Max text length before truncation |

## CLI Reference

### Memory Operations

```bash
HELIX="${HELIX_PLUGIN_ROOT:-$(cat .helix/plugin_root 2>/dev/null)}"

# Store insight
python3 "$HELIX/lib/memory/core.py" store \
  --content "When X, do Y because Z" --tags '["pattern"]'

# Recall by semantic similarity (graph expansion on by default)
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 3
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --graph-hops 0  # disable graph

# Get single insight
python3 "$HELIX/lib/memory/core.py" get "insight-name"

# Apply feedback with causal filtering
python3 "$HELIX/lib/memory/core.py" feedback \
  --names '["insight-1"]' --outcome delivered --causal-names '["insight-1"]'

# Decay dormant insights
python3 "$HELIX/lib/memory/core.py" decay --days 30

# Prune low performers
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3

# Health check (includes edge statistics)
python3 "$HELIX/lib/memory/core.py" health

# Graph neighbors for an insight
python3 "$HELIX/lib/memory/core.py" neighbors "insight-name" --limit 5
python3 "$HELIX/lib/memory/core.py" neighbors "insight-name" --relation similar
python3 "$HELIX/lib/memory/core.py" neighbors "insight-name" --relation led_to
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
python3 "$HELIX/lib/injection.py" batch-inject --tasks '["obj1", "obj2"]' --limit 3

# Strategic recall for orchestrator RECALL phase (broad sweep + summary)
python3 "$HELIX/lib/injection.py" strategic-recall "authentication and authorization patterns"
python3 "$HELIX/lib/injection.py" strategic-recall "objective" --limit 20 --min-relevance 0.25
```

## Slash Commands

| Command | Purpose |
|---------|---------|
| `/helix <objective>` | Full pipeline: recall → explore → plan → build → learn → complete |
| `/helix-meta-planner <objective>` | Plan-mode only: recall → explore → plan → synthesize → present for approval |
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
│   │   ├── common.py         # Shared run_hook() entry point
│   │   ├── inject_memory.py  # SubagentStart: injection + sideband
│   │   ├── extract_learning.py # SubagentStop: extraction + feedback
│   │   └── session_end.py    # SessionEnd: decay + prune + cleanup
│   ├── memory/
│   │   ├── __init__.py       # Exports 8 primitives
│   │   ├── core.py           # store, recall, get, feedback, decay, prune, count, health
│   │   ├── edges.py          # Graph: add_edges, get_neighbors, delete_edges_for
│   │   └── embeddings.py     # snowflake-arctic-embed-m-v1.5 (768-dim)
│   ├── db/
│   │   ├── __init__.py       # Exports get_db, write_lock, init_db
│   │   └── connection.py     # SQLite singleton, WAL, migrations v1-v12
│   ├── injection.py          # inject_context, format_prompt, batch_inject
│   ├── extraction.py         # process_completion, extract_insight, extract_outcome
│   └── build_loop.py         # DAG ops: cycles, readiness, stall, wait, status
├── scripts/
│   └── setup-env.sh          # SessionStart: venv + env + warmup
├── skills/
│   ├── helix/
│   │   └── SKILL.md          # Main orchestrator
│   ├── helix-meta-planner/
│   │   └── SKILL.md          # Plan-mode: insight-driven planning without execution
│   ├── helix-query/
│   │   └── SKILL.md          # Memory search
│   └── helix-stats/
│       └── SKILL.md          # Health check
├── tests/
│   ├── conftest.py           # Fixtures: test_db, mock_embeddings, isolated_env
│   ├── test_memory_core.py   # 57 tests — 8 primitives + hybrid search + ghost cleanup + user-provided
│   ├── test_injection.py     # 23 tests — inject_context, format_prompt, batch_inject
│   ├── test_extraction.py    # 36 tests — process_completion, last-match-wins
│   ├── test_inject_memory.py # 29 tests — SubagentStart hook + sideband roundtrip + cross-agent diversity
│   ├── test_extract_learning.py # 21 tests — SubagentStop hook
│   ├── test_extract_causal.py # 11 tests — causal filtering (real embeddings)
│   ├── test_build_loop.py    # 27 tests — DAG ops, wave management
│   ├── test_causal_feedback.py # 9 tests — dual-path feedback (real embeddings)
│   ├── test_relevance_gate.py # 5 tests — min_relevance filtering (real embeddings)
│   ├── test_strategic_recall.py # 18 tests — strategic_recall() for RECALL phase
│   ├── test_edges.py         # 14 tests — edge helpers (add, neighbors, delete, canonical)
│   ├── test_graph_memory.py  # 18 tests — graph integration (auto-link, expansion, provenance, prune)
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
