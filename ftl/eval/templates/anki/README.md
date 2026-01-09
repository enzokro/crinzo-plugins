# Mock Anki App — FTL Evaluation Anchor

Standardized flashcard app for FTL campaign evaluation. This README defines the fixed specification against which all eval runs are measured.

---

## REQUIRED TASK BREAKDOWN (TDD)

**Test-Driven Development**: Each task writes tests FIRST, then implements to make them pass.

**The planner MUST create exactly these 4 tasks. Do NOT merge, split, reorder, or add tasks.**

| Task | Slug | Description | Verify |
|------|------|-------------|--------|
| 001 | data-model | TDD: Test Card import → Implement Card dataclass + fastlite table | `uv run pytest test_app.py -k test_card_model -v` |
| 002 | routes-crud | TDD: Write CRUD tests (create, list, delete) → Implement routes | `uv run pytest test_app.py -k card -v` |
| 003 | routes-study | TDD: Write study tests (due, reveal, rate) → Implement routes + SM-2 | `uv run pytest test_app.py -k study -v` |
| 004 | integration | Verify all 6 tests pass, fix any failures | `uv run pytest test_app.py -v` |

**Dependencies:** 001 → 002 → 003 → 004 (sequential)

---

## TDD Protocol

Each builder task (001-003) follows this cycle:

```
1. RED:   Write test(s) that define expected behavior
2. GREEN: Implement minimal code to pass tests
3. VERIFY: Run tests, confirm pass
```

**Task 001** bootstraps test_app.py with pytest fixtures and the first test.
**Tasks 002-003** ADD tests to test_app.py, then implement.
**Task 004** runs full suite - if anything fails, fix it.

---

## Objective

Build a flashcard study app with spaced repetition using FastHTML and SQLite.

## Required Behavior

### 1. Data Model

```
Card:
  - id: int (primary key)
  - front: str (question text)
  - back: str (answer text)
  - next_review: date (when card is next due)
  - interval: int (days until next review, starts at 1)
```

**CRITICAL for fastlite with date fields**: Use `db.create(Card, pk="id", transform=True)` to enable automatic date conversion. Without `transform=True`, dates are stored as strings and comparisons fail.

**Date comparisons in queries**: Even with `transform=True`, compare dates using `date.today().isoformat()` in Python code.

### 2. Routes

| Route | Method | Behavior |
|-------|--------|----------|
| `/` | GET | Redirect to `/cards` |
| `/cards` | GET | List all cards with front text |
| `/cards/new` | GET | Form to create new card |
| `/cards/new` | POST | Create card, redirect to `/cards` |
| `/cards/{id}/delete` | POST | Delete card, redirect to `/cards` |
| `/study` | GET | Show next due card (front only), or "No cards due" |
| `/study/{id}/reveal` | POST | Show card back with rating buttons |
| `/study/{id}/rate` | POST | Apply SM-2 rating, update interval, redirect to `/study` |

### 3. Spaced Repetition (SM-2 Simplified)

Rating updates interval:
- **Again** (0): interval = 1
- **Hard** (1): interval = interval * 1.2
- **Good** (2): interval = interval * 2.0
- **Easy** (3): interval = interval * 3.0

After rating: `next_review = today + interval days`

### 4. Test Coverage (6 tests total)

Tests are written incrementally via TDD:

**Task 001** (1 test):
- `test_card_model` - Card dataclass can be imported and has required fields

**Task 002** (3 tests):
- `test_card_creation` - POST /cards/new creates card
- `test_card_listing` - GET /cards shows all cards
- `test_card_deletion` - POST /cards/{id}/delete removes card

**Task 003** (2 tests):
- `test_study_shows_due` - GET /study shows only due cards
- `test_rating_updates_interval` - POST /study/{id}/rate applies SM-2 correctly

## Verification Commands

```bash
# Full test suite
uv run pytest test_app.py -v

# Per-task verification
uv run pytest test_app.py -k test_card_model -v  # Task 001
uv run pytest test_app.py -k card -v              # Task 002
uv run pytest test_app.py -k study -v             # Task 003
```

## Success Criteria

1. All 6 tests pass
2. Each task followed TDD (test written before implementation)
3. No runtime errors

## Non-Goals (Out of Scope)

- User authentication
- Multiple decks
- Card editing (only create/delete)
- Import/export
- Styling beyond functional

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
