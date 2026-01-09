# Prior Knowledge (from previous campaigns)

This knowledge comes from successful campaigns. Use it to inform your planning.

## Meta-Patterns (high confidence)

**layered-build** (signal: +5)
- Pattern: data-model → crud-routes → algorithm-routes → test-suite
- Conditions: Works when each layer has clear inputs/outputs
- Use for: Sequential task dependencies with foundation-first approach

**fastlite-dataclass-sync** (signal: +4)
- Pattern: `db.create(Dataclass, pk="id")` creates both type and table
- Conditions: Simple schema, single table, clear primary key
- Use for: FastHTML apps with SQLite persistence

**post-redirect-get** (signal: +6)
- Pattern: POST handlers return `RedirectResponse(url, status_code=303)`
- Conditions: Form-based mutations that need refresh safety
- Use for: Any state-changing route (create, update, delete, rate)

## Known Failure Modes

**date-string-mismatch** (impact: ~70K tokens when hit)
- Issue: SQLite stores Python `date` objects as ISO strings
- Symptom: `card.next_review <= date.today()` fails silently
- Mitigation: Compare with `str(date.today())` or parse explicitly
- **WARN builders** when: Task involves date fields, next_review, or due-date filtering

## Verification Patterns

| Task Type | Verify Command |
|-----------|----------------|
| Data model | `python3 -c "from main import Model; print(Model)"` |
| Routes | `uv run pytest test_app.py -k <route_prefix>` |
| Full suite | `uv run pytest test_app.py -v` |

## How to Use This

1. **Reference patterns** in task design when they match
2. **Include warnings** in task Done-when for known failure modes
3. **Note in rationale**: "Pattern match: layered-build"
