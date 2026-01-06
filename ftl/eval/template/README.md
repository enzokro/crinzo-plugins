# Mock Anki App — FTL Evaluation Anchor

Standardized flashcard app for FTL campaign evaluation. This README defines the fixed specification against which all eval runs are measured.

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

### 4. Test Coverage

`test_app.py` must verify:
- [ ] Card creation via POST
- [ ] Card listing shows all cards
- [ ] Card deletion removes card
- [ ] Study shows only due cards
- [ ] Rating updates interval correctly
- [ ] next_review advances after rating

## Verification Commands

```bash
# Tests pass
uv run pytest test_app.py -v

# App starts without error
uv run python main.py
# → Serves on http://localhost:5001
```

## Success Criteria

1. All routes respond correctly
2. All tests pass
3. Cards advance through spaced repetition
4. No runtime errors

## Non-Goals (Out of Scope)

- User authentication
- Multiple decks
- Card editing (only create/delete)
- Import/export
- Styling beyond functional

---

This specification is FIXED. All FTL eval runs use identical starting conditions for meaningful comparison.
