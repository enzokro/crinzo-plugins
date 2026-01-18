# FTL Database Schema Reference

FTL uses SQLite via fastsql for all persistent storage. The database is located at `.ftl/ftl.db`.

## Tables Overview

| Table | Purpose |
|-------|---------|
| `memory` | Failures and patterns (polymorphic) |
| `memory_edge` | Graph edges for relationship traversal |
| `campaign` | Campaign state with embedded tasks |
| `workspace` | Workspace execution records |
| `archive` | Completed campaign archives |
| `exploration` | Aggregated explorer outputs |
| `explorer_result` | Individual explorer outputs (staging) |
| `plan` | Task plans from planner agent |
| `benchmark` | Performance benchmark results |
| `phase_state` | Workflow phase tracking (singleton) |
| `event` | Append-only audit log |

---

## Memory Table

Unified storage for failures and patterns.

```sql
CREATE TABLE memory (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,           -- Unique kebab-case slug
    type TEXT NOT NULL,           -- "failure" | "pattern"
    trigger TEXT NOT NULL,        -- Error message or condition
    resolution TEXT NOT NULL,     -- Fix (failure) or insight (pattern)
    match TEXT,                   -- Regex for log matching (failures only)
    cost INTEGER DEFAULT 0,       -- Tokens spent (failure) or saved (pattern)
    source TEXT DEFAULT '[]',     -- JSON: workspace IDs
    created_at TEXT NOT NULL,     -- ISO timestamp
    last_accessed TEXT,           -- ISO timestamp
    access_count INTEGER DEFAULT 0,
    times_helped INTEGER DEFAULT 0,
    times_failed INTEGER DEFAULT 0,
    importance REAL DEFAULT 0.0,  -- Pre-computed ranking score
    related_typed TEXT DEFAULT '{}',       -- JSON: {rel_type: [names]}
    cross_relationships TEXT DEFAULT '{}', -- JSON: {rel_type: [names]}
    embedding BLOB                -- 1536 bytes (384 floats × 4 bytes)
);

CREATE INDEX idx_memory_type_importance ON memory(type, importance DESC);
CREATE INDEX idx_memory_name ON memory(name);
```

### Embedding Storage

Embeddings are stored as BLOBs using IEEE 754 float32 format:
- Model: `all-MiniLM-L6-v2` (384 dimensions)
- Size: 384 × 4 = 1,536 bytes per embedding
- Serialization: `struct.pack(f'{384}f', *embedding)`

---

## Memory Edge Table

Graph edges for BFS traversal of relationships.

```sql
CREATE TABLE memory_edge (
    id INTEGER PRIMARY KEY,
    from_id INTEGER NOT NULL,     -- FK → memory.id
    to_id INTEGER NOT NULL,       -- FK → memory.id
    rel_type TEXT NOT NULL,       -- Relationship type
    weight REAL DEFAULT 0.8,      -- Edge weight for path pruning
    created_at TEXT NOT NULL
);

CREATE INDEX idx_edge_from ON memory_edge(from_id, rel_type);
CREATE INDEX idx_edge_to ON memory_edge(to_id);
```

### Relationship Types

| Type | Weight | Description |
|------|--------|-------------|
| `co_occurs` | 0.8 | Seen together in same campaign |
| `causes` | 1.0 | A causes B |
| `solves` | 1.5 | Pattern solves failure |
| `prerequisite` | 1.0 | A must happen before B |
| `variant` | 0.7 | Similar variations |

---

## Campaign Table

Campaign state with embedded task DAG.

```sql
CREATE TABLE campaign (
    id INTEGER PRIMARY KEY,
    objective TEXT NOT NULL,
    framework TEXT,
    status TEXT DEFAULT 'active',        -- "active" | "complete"
    created_at TEXT NOT NULL,
    completed_at TEXT,
    tasks TEXT DEFAULT '[]',             -- JSON: task array
    summary TEXT DEFAULT '{}',           -- JSON: completion summary
    fingerprint TEXT DEFAULT '{}',       -- JSON: similarity fingerprint
    patterns_extracted TEXT DEFAULT '[]', -- JSON: pattern names
    objective_embedding BLOB             -- 1536 bytes for similarity
);

CREATE INDEX idx_campaign_status ON campaign(status);
```

### Task JSON Structure

```json
{
    "seq": "001",
    "slug": "task-name",
    "type": "BUILD",
    "depends": "none" | "001" | ["001", "002"],
    "status": "pending" | "in_progress" | "complete" | "blocked"
}
```

---

## Workspace Table

Workspace execution records (replaces XML files).

```sql
CREATE TABLE workspace (
    id INTEGER PRIMARY KEY,
    workspace_id TEXT NOT NULL UNIQUE,  -- "001-slug" format
    campaign_id INTEGER NOT NULL,       -- FK → campaign.id
    seq TEXT NOT NULL,
    slug TEXT NOT NULL,
    status TEXT DEFAULT 'active',       -- "active" | "complete" | "blocked"
    created_at TEXT NOT NULL,
    completed_at TEXT,
    blocked_at TEXT,
    objective TEXT,
    delta TEXT DEFAULT '[]',            -- JSON: files to modify
    verify TEXT,
    verify_source TEXT,
    budget INTEGER DEFAULT 5,
    framework TEXT,
    framework_confidence REAL DEFAULT 1.0,
    idioms TEXT DEFAULT '{}',           -- JSON: {required, forbidden}
    prior_knowledge TEXT DEFAULT '{}',  -- JSON: injected memories
    lineage TEXT DEFAULT '{}',          -- JSON: parent references
    delivered TEXT,
    utilized_memories TEXT DEFAULT '[]', -- JSON: feedback tracking
    code_contexts TEXT DEFAULT '[]',    -- JSON: code snapshots
    preflight TEXT DEFAULT '[]'         -- JSON: preflight checks
);

CREATE INDEX idx_workspace_campaign ON workspace(campaign_id);
CREATE INDEX idx_workspace_status ON workspace(status);
```

---

## Archive Table

Lightweight archive for `find_similar()`.

```sql
CREATE TABLE archive (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER NOT NULL,
    objective TEXT NOT NULL,
    objective_preview TEXT,         -- First 100 chars
    framework TEXT,
    completed_at TEXT NOT NULL,
    fingerprint TEXT DEFAULT '{}',
    objective_embedding BLOB,
    outcome TEXT DEFAULT 'complete', -- "complete" | "partial"
    summary TEXT DEFAULT '{}',
    patterns_extracted TEXT DEFAULT '[]'
);

CREATE INDEX idx_archive_framework ON archive(framework);
```

---

## Exploration Table

Aggregated explorer outputs.

```sql
CREATE TABLE exploration (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER,
    objective TEXT,
    git_sha TEXT,
    created_at TEXT NOT NULL,
    structure TEXT DEFAULT '{}',    -- JSON: structure mode result
    pattern TEXT DEFAULT '{}',      -- JSON: pattern mode result
    memory TEXT DEFAULT '{}',       -- JSON: memory mode result
    delta TEXT DEFAULT '{}',        -- JSON: delta mode result
    modes_completed INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending'
);
```

---

## Explorer Result Table

Individual explorer outputs before aggregation. Used for session-based quorum tracking.

```sql
CREATE TABLE explorer_result (
    id INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,       -- UUID linking parallel explorers
    mode TEXT NOT NULL,             -- "structure" | "pattern" | "memory" | "delta"
    status TEXT DEFAULT 'pending',  -- "pending" | "ok" | "partial" | "error"
    result TEXT DEFAULT '{}',       -- JSON: mode-specific output
    created_at TEXT NOT NULL
);

CREATE INDEX idx_explorer_result_session ON explorer_result(session_id);
```

---

## Plan Table

Task plans from the planner agent.

```sql
CREATE TABLE plan (
    id INTEGER PRIMARY KEY,
    campaign_id INTEGER,            -- FK → campaign.id (optional)
    objective TEXT NOT NULL,
    framework TEXT,
    idioms TEXT DEFAULT '{}',       -- JSON: {required, forbidden}
    tasks TEXT DEFAULT '[]',        -- JSON: task array
    created_at TEXT NOT NULL,
    status TEXT DEFAULT 'active'    -- "active" | "executed" | "superseded"
);

CREATE INDEX idx_plan_status ON plan(status);
CREATE INDEX idx_plan_campaign ON plan(campaign_id);
```

---

## Benchmark Table

Performance benchmark results.

```sql
CREATE TABLE benchmark (
    id INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,           -- UUID for benchmark run
    metric TEXT NOT NULL,           -- Metric name (memory_size, query_time, etc)
    value REAL NOT NULL,            -- Metric value
    metadata TEXT DEFAULT '{}',     -- JSON: additional data
    created_at TEXT NOT NULL
);

CREATE INDEX idx_benchmark_run ON benchmark(run_id);
```

---

## Phase State Table

Workflow phase tracking (singleton pattern).

```sql
CREATE TABLE phase_state (
    id INTEGER PRIMARY KEY,
    phase TEXT DEFAULT 'none',      -- Current phase
    started_at TEXT,
    transitions TEXT DEFAULT '[]'   -- JSON: [{from, to, at}]
);
```

---

## Event Table

Append-only audit log.

```sql
CREATE TABLE event (
    id INTEGER PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    metadata TEXT DEFAULT '{}'      -- JSON: event-specific data
);

CREATE INDEX idx_event_timestamp ON event(timestamp);
```

---

## Usage Examples

### Query memories by type and importance

```python
from lib.db import get_db

db = get_db()
memories = db.t.memory

# Get top 5 failures by importance
failures = list(memories.rows_where(
    "type = ? ORDER BY importance DESC LIMIT 5",
    ["failure"]
))
```

### Update workspace status

```python
workspaces = db.t.workspace
workspaces.update({
    "status": "complete",
    "completed_at": datetime.now().isoformat(),
    "delivered": "Task completed successfully"
}, workspace_id)
```

### Semantic search with embeddings

```python
from lib.db.embeddings import embed, embed_to_blob, cosine_similarity_blob

query_emb = embed("import error")
query_blob = embed_to_blob(query_emb)

for row in db.t.memory.rows:
    if row.get("embedding"):
        sim = cosine_similarity_blob(query_blob, row["embedding"])
        if sim > 0.5:
            print(f"{row['name']}: {sim:.3f}")
```

---

## Migration Notes

### From JSON/XML to SQLite

The database backend is a **clean break** - no migration path from previous JSON/XML storage:

1. **Memory**: Previously `.ftl/memory.json` → Now `memory` table
2. **Campaigns**: Previously `.ftl/campaign.json` → Now `campaign` table
3. **Workspaces**: Previously `.ftl/workspace/*.xml` → Now `workspace` table
4. **Explorations**: Previously `.ftl/exploration.json` → Now `exploration` table

### API Preservation

All public function signatures preserved exactly:
- `add_failure(failure: dict, path, validate)` - `path` ignored
- `workspace.create(plan, task_seq) -> list[Path]` - Returns virtual paths
- `workspace.complete(path, delivered, utilized) -> Path` - Accepts Path, returns Path
