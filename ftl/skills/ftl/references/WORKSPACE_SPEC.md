# Workspace Specification

Complete specification for workspace lifecycle, database schema, and sibling failure injection.

---

## Storage Backend

All workspace data is stored in `.ftl/ftl.db` SQLite database. The CLI maintains backward compatibility by accepting and returning Path-like workspace identifiers.

```
.ftl/
├── ftl.db                             # SQLite database (ALL persistent state)
│   ├── workspace table                # Workspace execution records
│   ├── campaign table                 # Campaign state with DAG
│   ├── memory table                   # Failures and patterns
│   ├── exploration table              # Aggregated explorer outputs
│   ├── explorer_result table          # Session-based explorer staging
│   ├── plan table                     # Stored plans from planner
│   └── ...
├── ftl.log                            # Debug logs
└── plugin_root                        # Plugin path marker
```

### Virtual Paths

The workspace API accepts and returns virtual paths for CLI compatibility:
- Input: `001_slug_active.xml` or `001_slug_active`
- Storage: `workspace` table with `workspace_id = "001-slug"` and `status = "active"`
- Output: `Path(".ftl/workspace/001_slug_active.xml")` (virtual, data is in DB)

---

## Naming Convention

```
{SEQ}_{slug}_{status}.xml
```

| Component | Format | Example |
|-----------|--------|---------|
| `SEQ` | 3-digit sequence | `001`, `002`, `003` |
| `slug` | Kebab-case task name | `spec-routes`, `impl-models` |
| `status` | State indicator | `active`, `complete`, `blocked` |

**Examples:**
- `001_spec-routes_active.xml` — Task 001, currently executing
- `002_impl-models_complete.xml` — Task 002, finished successfully
- `003_auth-handler_blocked.xml` — Task 003, failed and captured

---

## Lifecycle States

```
                    ┌─────────────┐
                    │   active    │
                    └──────┬──────┘
                           │
              ┌────────────┴────────────┐
              │                         │
              ▼                         ▼
       ┌─────────────┐           ┌─────────────┐
       │  complete   │           │   blocked   │
       └─────────────┘           └─────────────┘
```

### active

- Workspace created, builder executing
- File: `NNN_slug_active.xml`
- Transitions to: `complete` or `blocked`

### complete

- Builder finished, deliverables produced
- Status updated to `complete` in database
- `completed_at` timestamp added
- `delivered` field populated with summary

### blocked

- Builder encountered unrecoverable issue
- Status updated to `blocked` in database
- `blocked_at` timestamp added
- `delivered` field contains `BLOCKED: {reason}`

**Key insight**: Blocking is success at information capture. The workspace records what failed and why, enabling Observer pattern extraction.

---

## Database Fields

Workspace data is stored in the `workspace` table in `.ftl/ftl.db`. The XML-style virtual paths are for CLI compatibility only.

### Core Fields

| Field | Type | Description |
|-------|------|-------------|
| `workspace_id` | TEXT | `{SEQ}-{slug}` format, UNIQUE |
| `campaign_id` | INT | Foreign key to campaigns table |
| `seq` | TEXT | 3-digit sequence number |
| `slug` | TEXT | Kebab-case task name |
| `status` | TEXT | `active`, `complete`, or `blocked` |
| `created_at` | TEXT | ISO 8601 timestamp |
| `completed_at` | TEXT | ISO 8601 timestamp (on complete) |
| `blocked_at` | TEXT | ISO 8601 timestamp (on blocked) |

### Task Fields

| Field | Type | Description |
|-------|------|-------------|
| `objective` | TEXT | User's original intent |
| `delta` | TEXT (JSON) | Files to modify `["path1", "path2"]` |
| `creates` | TEXT (JSON) | Files to create (exempt from existence check) `["path"]` |
| `verify` | TEXT | Verification command |
| `verify_source` | TEXT | Optional test file to read |
| `budget` | INT | Tool call budget |
| `preflight` | TEXT (JSON) | Pre-checks `["cmd1", "cmd2"]` |

**Note on `creates`**: For BUILD tasks that create new files, list them in `creates` to exempt them from the delta existence validation. Files in `delta` that are also in `creates` won't trigger "delta_not_found" validation errors.

### Context Fields

| Field | Type | Description |
|-------|------|-------------|
| `framework` | TEXT | Detected framework name |
| `framework_confidence` | REAL | Confidence score 0.0-1.0 |
| `idioms` | TEXT (JSON) | `{"required": [...], "forbidden": [...]}` |
| `prior_knowledge` | TEXT (JSON) | Injected failures and patterns |
| `lineage` | TEXT (JSON) | Parent task references |
| `code_contexts` | TEXT (JSON) | Code snippets for delta files |

### Output Fields

| Field | Type | Description |
|-------|------|-------------|
| `delivered` | TEXT | Builder output summary (or `BLOCKED: reason`) |
| `utilized_memories` | TEXT (JSON) | Memories that were helpful |

### Field Mapping from Conceptual XML

For reference, the conceptual XML elements map to database fields:

| XML Element | Database Field |
|-------------|----------------|
| `<objective>` | `objective` |
| `<implementation><delta>` | `delta` (JSON array) |
| `<implementation><verify>` | `verify` |
| `<implementation><budget>` | `budget` |
| `<idioms>` | `idioms` (JSON object) |
| `<prior_knowledge>` | `prior_knowledge` (JSON object) |
| `<lineage>` | `lineage` (JSON object) |
| `<delivered>` | `delivered` |
| `<memory_utilization>` | `utilized_memories` (JSON array) |

---

## Element Reference

### objective

The user's original intent — WHY this task exists.

```xml
<objective>Add CRUD routes for user management</objective>
```

### implementation

Specifies WHAT to do and HOW to verify.

| Element | Required | Description |
|---------|----------|-------------|
| `delta` | Yes | Files to modify (multiple allowed) |
| `verify` | Yes | Command to verify success |
| `verify_source` | No | Test file to read before implementing |
| `budget` | Yes | Tool call budget for builder |
| `preflight` | No | Pre-checks before implementation |

### code_context

Relevant code snippets for delta files.

```xml
<code_context path="src/routes.py" lines="45-120">
  <content>def get_user(id): ...</content>
  <exports>get_user(), create_user()</exports>
  <imports>from fasthtml import FT, Div</imports>
</code_context>
```

Multiple `code_context` elements for multi-file deltas.

### idioms

Framework-specific constraints (non-negotiable).

```xml
<idioms framework="FastHTML" confidence="0.85">
  <required>use @rt decorator for routes</required>
  <forbidden>raw HTML string construction</forbidden>
</idioms>
```

Builder MUST follow idioms even if tests pass without them.

### prior_knowledge

Failures and patterns from memory + siblings.

**Failure:**
```xml
<failure name="import-order" cost="2500" injected="true">
  <trigger>ImportError: cannot import name 'FT'</trigger>
  <fix>Import FT from fasthtml.common, not fasthtml</fix>
  <match>ImportError.*FT</match>
</failure>
```

**Pattern:**
```xml
<pattern name="stubs-in-first-build" saved="2293760000" injected="true">
  <trigger>Building implementation without test file</trigger>
  <insight>Read verify_source first to understand expected behavior</insight>
</pattern>
```

### lineage

Parent task deliveries for DAG awareness.

```xml
<lineage>
  <parent seq="001" workspace="001_spec-routes_complete">
    <prior_delivery>Test stubs created for CRUD operations</prior_delivery>
  </parent>
</lineage>
```

Supports multiple parents for DAG convergence (task depends on 2+ parents).

### delivered

Builder's output summary.

- Empty on creation
- Populated on complete: Description of what was delivered
- Populated on blocked: `BLOCKED: {reason}`

### memory_utilization

Tracks which prior knowledge was actually helpful (for feedback loop).

```xml
<memory_utilization>
  <utilized name="import-order" type="failure"/>
  <utilized name="stubs-in-first-build" type="pattern"/>
</memory_utilization>
```

---

## Sibling Failure Injection

Enables intra-campaign learning: failures from one branch inform parallel branches.

### Timing

| Event | What Happens |
|-------|--------------|
| Plan created | Tasks defined with dependencies, no workspaces yet |
| Task 001 starts | Workspace created with `memory.get_context()` only |
| Task 001 blocks | Workspace status set to `blocked` in database |
| Task 002 starts | Workspace created with memory + sibling failures from 001 |

### Implementation

```python
def create(plan, task_seq):
    # 1. Get memory context
    memory_ctx = memory.get_context(
        task_type=task.get("type", "BUILD"),
        tags=[framework.lower()] if framework else None,
        objective=task_context
    )
    memory_failures = memory_ctx.get("failures", [])

    # 2. Query for sibling failures from database
    sibling_failures = get_sibling_failures(campaign_id)

    # 3. Combine and inject
    all_failures = memory_failures + sibling_failures
    inject_into_prior_knowledge(workspace, all_failures)

def get_sibling_failures(campaign_id: int) -> list:
    """Query blocked workspaces in same campaign for failure injection."""
    db = get_db()
    blocked = list(db.t.workspace.rows_where(
        "campaign_id = ? AND status = ?",
        [campaign_id, "blocked"]
    ))

    failures = []
    for ws in blocked:
        delivered = ws.get("delivered", "")
        if "BLOCKED:" in delivered:
            reason = delivered.split("BLOCKED:", 1)[1].strip()
            failures.append({
                "name": f"sibling-{ws['workspace_id']}",
                "trigger": reason.split('\n')[0],
                "fix": "See blocked workspace for attempted fixes",
                "cost": 1000,
                "source": [ws["workspace_id"]]
            })
    return failures
```

### Why At Creation Time?

The planner runs once BEFORE any building starts. Sibling failures only exist AFTER builders encounter them.

Dynamic injection at workspace creation ensures:
1. **Freshness**: Latest failures from concurrent branches
2. **Relevance**: Only failures from same campaign
3. **Context**: Failures include workspace stem for traceability

### Memory vs Sibling Failures

| Attribute | Memory Failures | Sibling Failures |
|-----------|-----------------|------------------|
| Source | Historical `memory` table | Current campaign blocked workspaces |
| Relevance scoring | Semantic similarity | Always injected |
| `injected` attribute | `"true"` | `"false"` |
| Feedback tracking | Yes (`times_helped/failed`) | No (ephemeral) |

---

## Transaction Safety

Workspace operations use SQLite transactions for data integrity:

```python
def complete(workspace_id, delivered, utilized=None):
    db = get_db()
    workspace = db.t.workspace.get(workspace_id)
    workspace.status = "complete"
    workspace.completed_at = datetime.now().isoformat()
    workspace.delivered = delivered
    if utilized:
        workspace.utilized_memories = json.dumps(utilized)
    db.t.workspace.update(workspace)
    # SQLite ACID guarantees atomicity
```

All database operations are protected by SQLite's ACID properties, replacing the previous file-based atomic writes.

---

## State Synchronization

Workspace status operations automatically sync to campaign task status:

```
workspace.complete() → workspace.status = "complete"
                    → campaign.tasks[seq].status = "complete"

workspace.block()   → workspace.status = "blocked"
                    → campaign.tasks[seq].status = "blocked"
```

**Design principle**: Workspace is the single source of truth for task status. This makes state desync impossible — there's only one API to call.

The sync extracts `seq` from `workspace_id` (format: `{seq}-{slug}`) and updates the corresponding campaign task. If no active campaign exists or the task isn't found, the sync silently succeeds (allowing standalone workspace operations).

**Lineage population**: When child workspaces are created, `_build_lineage()` queries parent workspaces by seq + "complete" status. The auto-sync ensures parent tasks are marked complete in the workspace table before children are created, guaranteeing lineage data is available.

---

## CLI Commands

| Command | Description |
|---------|-------------|
| `workspace.py create --plan-id ID [--task SEQ]` | Create workspace(s) from stored plan |
| `workspace.py complete PATH --delivered "summary"` | Mark workspace complete |
| `workspace.py block PATH --reason "why"` | Mark workspace blocked |
| `workspace.py parse PATH` | Parse workspace to JSON |

See [CLI_REFERENCE.md](CLI_REFERENCE.md) for complete syntax.
