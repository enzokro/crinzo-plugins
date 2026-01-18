# Workspace Specification

Complete specification for workspace lifecycle, database schema, and sibling failure injection.

---

## Storage Backend

All workspace data is stored in `.ftl/ftl.db` SQLite database. The CLI maintains backward compatibility by accepting and returning Path-like workspace identifiers.

```
.ftl/
├── ftl.db                             # SQLite database (all persistent state)
│   ├── workspace table                # Workspace execution records
│   ├── campaign table                 # Campaign state with DAG
│   ├── memory table                   # Failures and patterns
│   ├── exploration table              # Aggregated explorer outputs
│   └── ...
├── cache/
│   └── explorer_*.json                # Temporary explorer outputs (intermediate)
├── plan.json                          # Current plan (transient)
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
- File renamed: `NNN_slug_complete.xml`
- `completed_at` timestamp added
- `delivered` field populated with summary

### blocked

- Builder encountered unrecoverable issue
- File renamed: `NNN_slug_blocked.xml`
- `blocked_at` timestamp added
- `delivered` field contains `BLOCKED: {reason}`

**Key insight**: Blocking is success at information capture. The workspace records what failed and why, enabling Observer pattern extraction.

---

## XML Schema

### Root Element

```xml
<workspace id="003-routes-crud" status="active" _schema_version="1.0" created_at="2024-01-15T10:30:00">
  <!-- Content -->
</workspace>
```

| Attribute | Required | Description |
|-----------|----------|-------------|
| `id` | Yes | `{SEQ}-{slug}` format |
| `status` | Yes | `active`, `complete`, or `blocked` |
| `_schema_version` | Yes | Schema version (currently "1.0") |
| `created_at` | Yes | ISO 8601 timestamp |
| `completed_at` | On complete | ISO 8601 timestamp |
| `blocked_at` | On blocked | ISO 8601 timestamp |

### Full Schema

```xml
<workspace id="003-routes-crud" status="active" _schema_version="1.0" created_at="...">

  <!-- WHY this task exists -->
  <objective>Add CRUD routes for user management</objective>

  <!-- WHAT to do and HOW to verify -->
  <implementation>
    <delta>src/routes.py</delta>
    <delta>src/models.py</delta>
    <verify>pytest routes/test_*.py -v</verify>
    <verify_source>routes/test_crud.py</verify_source>
    <budget>5</budget>
    <preflight>python -c "import fasthtml"</preflight>
  </implementation>

  <!-- Code context for delta files -->
  <code_context path="src/routes.py" lines="45-120">
    <content>...</content>
    <exports>get_user(), create_user()</exports>
    <imports>from fasthtml import ...</imports>
  </code_context>

  <!-- Framework constraints -->
  <idioms framework="FastHTML" confidence="0.85">
    <required>use @rt decorator for routes</required>
    <forbidden>raw HTML string construction</forbidden>
  </idioms>

  <!-- Framework confidence (standalone) -->
  <framework_confidence>0.85</framework_confidence>

  <!-- Prior knowledge from memory + siblings -->
  <prior_knowledge>
    <failure name="import-order" cost="2500" injected="true">
      <trigger>ImportError: cannot import name 'FT'</trigger>
      <fix>Import FT from fasthtml.common, not fasthtml</fix>
      <match>ImportError.*FT</match>
    </failure>
    <pattern name="stubs-in-first-build" saved="2293760000" injected="true">
      <trigger>Building implementation without test file</trigger>
      <insight>Read verify_source first to understand expected behavior</insight>
    </pattern>
  </prior_knowledge>

  <!-- Parent task deliveries (DAG lineage) -->
  <lineage>
    <parent seq="001" workspace="001_spec-routes_complete">
      <prior_delivery>Test stubs created for CRUD operations</prior_delivery>
    </parent>
    <parent seq="002" workspace="002_impl-models_complete">
      <prior_delivery>User model with validation implemented</prior_delivery>
    </parent>
  </lineage>

  <!-- Builder output (empty until complete/blocked) -->
  <delivered></delivered>

  <!-- Memory utilization tracking (on complete) -->
  <memory_utilization>
    <utilized name="import-order" type="failure"/>
  </memory_utilization>

</workspace>
```

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
| Task 001 blocks | Failure recorded in `001_slug_blocked.xml` |
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

    # 2. Scan for sibling failures
    sibling_failures = get_sibling_failures(WORKSPACE_DIR)

    # 3. Combine and inject
    all_failures = memory_failures + sibling_failures
    inject_into_prior_knowledge(workspace, all_failures)

def get_sibling_failures(workspace_dir):
    failures = []
    for blocked_path in workspace_dir.glob("*_blocked.xml"):
        blocked_data = parse(blocked_path)
        delivered = blocked_data.get("delivered", "")

        if "BLOCKED:" in delivered:
            reason = delivered.split("BLOCKED:", 1)[1].strip()
            failures.append({
                "name": f"sibling-{blocked_path.stem}",
                "trigger": reason.split('\n')[0],
                "fix": "See blocked workspace for attempted fixes",
                "cost": 1000,
                "source": [blocked_path.stem]
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

## CLI Commands

| Command | Description |
|---------|-------------|
| `workspace.py create --plan plan.json [--task SEQ]` | Create workspace(s) from plan |
| `workspace.py complete PATH --delivered "summary"` | Mark workspace complete |
| `workspace.py block PATH --reason "why"` | Mark workspace blocked |
| `workspace.py parse PATH` | Parse workspace to JSON |

See [CLI_REFERENCE.md](CLI_REFERENCE.md) for complete syntax.
