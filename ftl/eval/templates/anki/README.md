# Mock Anki App — FTL Evaluation Anchor

Standardized flashcard app for FTL campaign evaluation. This README defines the fixed specification against which all eval runs are measured.

---

## REQUIRED TASK BREAKDOWN (Spec-First TDD)

**True TDD**: Spec Phase completes test scaffold. Build Phase implements to pass them.

**Test scaffold provided**: `test_app.py` contains fixtures + test signatures + docstrings.
SPEC task fills in assertions. This saves ~200K tokens vs writing from scratch.

**Mutable Tests**: BUILD tasks may adjust test assertions if the behavioral CONTRACT is preserved.
See "Mutable Tests Principle" section below.

**The planner MUST create exactly these 5 tasks. Do NOT merge, split, reorder, or add tasks.**

| Task | Type | Slug | Description | Delta | Verify |
|------|------|------|-------------|-------|--------|
| 000 | SPEC | test-spec | Complete test_app.py scaffold: fill in assertions for all 6 tests, implement db_with_card fixture | test_app.py | `uv run pytest test_app.py --collect-only` |
| 001 | BUILD | data-model | Implement Card dataclass + fastlite table to pass test_card_model | main.py, test_app.py | `uv run pytest test_app.py -k test_card_model -v` |
| 002 | BUILD | routes-crud | Implement CRUD routes to pass card tests | main.py, test_app.py | `uv run pytest test_app.py -k card -v` |
| 003 | BUILD | routes-study | Implement study routes + SM-2 to pass study tests | main.py, test_app.py | `uv run pytest test_app.py -k study -v` |
| 004 | VERIFY | integration | Verify all 6 tests pass, fix any remaining failures | any | `uv run pytest test_app.py -v` |

**Dependencies:** 000 → 001 → 002 → 003 → 004 (sequential)

---

## TDD Protocol (Scaffold-Based)

The key insight: **The agent that writes tests should NOT be the agent that passes them.**

```
SPEC PHASE (Task 000):
  - Scaffold exists with fixtures + test signatures
  - Complete assertions in each test (use RELATIVE assertions - see below)
  - Implement db_with_card fixture (return actual ID, not assumed)
  - Tests WILL fail (RED state)

BUILD PHASE (Tasks 001-003):
  - Each Builder has pre-existing Verify
  - Implement minimal code to pass tests (GREEN)
  - MAY adjust test assertions if implementation requires (tests are mutable)
  - Contract (behavior) is fixed; implementation (assertions) is adjustable

VERIFY PHASE (Task 004):
  - Integration check
  - Fix any remaining issues
```

**Scaffold provides**: Fixtures, test signatures, docstrings with expected behavior.
**Task 000** completes test_app.py by filling in assertions and the db_with_card fixture.
**Tasks 001-003** implement code to make tests pass (may adjust tests if needed).
**Task 004** runs full suite - if anything fails, fix it.

---

## Mutable Tests Principle

BUILD tasks may adjust test assertions if:
1. The behavioral **CONTRACT** is preserved (what the test verifies)
2. The **IMPLEMENTATION** is adjusted (how it verifies)

**Example - Contract vs Implementation:**
- Contract: "Card deletion removes the card from database"
- Implementation: `assert db[Card].get(card_id) is None` (adjustable based on actual API)

**Why this matters:** If SPEC phase wrote assertions with incorrect assumptions (e.g., assumed ID=1 when SQLite gave ID=4), Builder SHOULD fix the test rather than implementing convoluted workarounds in app code.

**Test Design Principles (for SPEC phase):**
1. Never assume specific IDs - use what fixtures return (`card_id` from `db_with_card`)
2. Never assume specific counts - use relative changes
3. Never assume clean state - fixtures provide isolation

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

All tests written in **Task 000** (SPEC phase). Builders implement to pass them.

**test_card_model** - Card dataclass can be imported and has required fields
- Verified by: Task 001

**test_card_creation** - POST /cards/new creates card
**test_card_listing** - GET /cards shows all cards
**test_card_deletion** - POST /cards/{id}/delete removes card
- Verified by: Task 002

**test_study_shows_due** - GET /study shows only due cards
**test_rating_updates_interval** - POST /study/{id}/rate applies SM-2 correctly
- Verified by: Task 003

## Verification Commands

```bash
# Task 000: Verify tests are collected (will fail when run - expected)
uv run pytest test_app.py --collect-only

# Task 001: Data model tests
uv run pytest test_app.py -k test_card_model -v

# Task 002: CRUD tests
uv run pytest test_app.py -k card -v

# Task 003: Study tests
uv run pytest test_app.py -k study -v

# Task 004: Full suite
uv run pytest test_app.py -v
```

## Success Criteria

1. All 6 tests pass after Task 004
2. Tests were written in SPEC phase (Task 000) before implementation
3. Each BUILD task only implements, never writes tests
4. No runtime errors

## Non-Goals (Out of Scope)

- User authentication
- Multiple decks
- Card editing (only create/delete)
- Import/export
- Styling beyond functional

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
