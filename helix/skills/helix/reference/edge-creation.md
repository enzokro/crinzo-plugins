# Edge Creation

## Schema

Edges connect related insights in the `memory_edge` table:

```sql
CREATE TABLE memory_edge (
    id INTEGER PRIMARY KEY,
    from_name TEXT NOT NULL,  -- Source insight name
    to_name TEXT NOT NULL,    -- Target insight name
    rel_type TEXT NOT NULL,   -- Relationship type
    weight REAL DEFAULT 1.0,  -- Strength (max 10.0)
    created_at TEXT NOT NULL,
    UNIQUE(from_name, to_name, rel_type)
);
```

## Edge Types

| Type | Meaning | Example |
|------|---------|---------|
| `similar` | Conceptually related insights | Two debugging patterns for same issue |
| `solves` | One insight addresses another | Pattern solves a failure |
| `causes` | One insight leads to another | Debugging reveals root cause |
| `co_occurs` | Often used together | Build patterns that pair well |

## Creating Edges via SQL

```bash
sqlite3 .helix/helix.db "INSERT INTO memory_edge (from_name, to_name, rel_type, weight, created_at)
VALUES ('pattern-name', 'failure-name', 'solves', 1.0, datetime('now'))"
```

## Creating Edges via Python

```python
from lib.db.connection import get_db, write_lock

conn = get_db()
with write_lock():
    conn.execute(
        "INSERT OR IGNORE INTO memory_edge (from_name, to_name, rel_type, weight, created_at) VALUES (?, ?, ?, 1.0, datetime('now'))",
        (from_name, to_name, rel_type)
    )
    conn.commit()
```

## Querying Edges

```bash
# All edges from an insight
sqlite3 .helix/helix.db "SELECT to_name, rel_type, weight FROM memory_edge WHERE from_name = 'insight-name'"

# All edges to an insight
sqlite3 .helix/helix.db "SELECT from_name, rel_type, weight FROM memory_edge WHERE to_name = 'insight-name'"

# Edges by type
sqlite3 .helix/helix.db "SELECT from_name, to_name, weight FROM memory_edge WHERE rel_type = 'solves'"
```

## When to Create Edges

- **similar**: Two insights address the same domain or problem space
- **solves**: A pattern insight directly addresses a debugging insight
- **causes**: Investigating one issue revealed another
- **co_occurs**: Multiple insights were injected together and both helped

## Weight Mechanics

- Default weight: 1.0
- Repeated edge creation increments weight (capped at 10.0)
- Higher weight = stronger relationship
