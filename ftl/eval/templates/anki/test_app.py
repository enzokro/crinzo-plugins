"""
Anki Flashcard App Test Suite - Scaffold

This scaffold provides:
- Fixtures for app/client/db setup
- Test function signatures with docstrings
- Import structure

SPEC task (000) fills in the actual assertions.
BUILD tasks (001-003) implement code to pass these tests.
BUILD tasks MAY adjust assertions if the CONTRACT is preserved.

## CRITICAL: Relative Assertions

Tests MUST use values returned by fixtures, NOT hardcoded assumptions.

BAD:  card_id = 1  # Assumes first card always has id=1
GOOD: db, Card, card_id = db_with_card  # Uses actual ID

BAD:  assert db[Card].count() == 1  # Assumes starting count
GOOD: count_before = db[Card].count(); ...; assert db[Card].count() == count_before + 1

The fixture returns (db, Card, card_id) - always use card_id, never assume it equals 1.
"""
import pytest
from datetime import date, timedelta


# =============================================================================
# FIXTURES - Pre-configured for fasthtml testing
# =============================================================================

@pytest.fixture
def app_components():
    """
    Deferred import fixture - allows tests to be collected before main.py exists.

    Returns tuple: (app, db, Card)

    Usage in tests:
        app, db, Card = app_components
    """
    try:
        from main import app, db, Card
        return app, db, Card
    except ImportError:
        pytest.skip("main.py not yet implemented")


@pytest.fixture
def client(app_components):
    """
    Test client for making HTTP requests.

    Uses Starlette's TestClient via fasthtml.
    """
    from starlette.testclient import TestClient
    app, db, Card = app_components
    return TestClient(app)


@pytest.fixture
def db_with_card(app_components):
    """
    Database with one test card already inserted.

    Returns tuple: (db, Card, card_id)  # card_id is the ACTUAL ID assigned

    Card has:
    - front: "Test Question"
    - back: "Test Answer"
    - next_review: today (due now)
    - interval: 1

    IMPORTANT: card_id may NOT be 1 (SQLite auto-increment persists).
    Always use the returned card_id, never assume a specific value.
    """
    app, db, Card = app_components
    # SPEC task: implement card insertion and return actual ID
    # Example (adjust API as needed):
    #   card = Card(front="Test Question", back="Test Answer",
    #               next_review=date.today(), interval=1)
    #   db[Card].insert(card)
    #   # Get the actual ID assigned
    #   yield db, Card, card.id
    #   # Optional cleanup
    pytest.skip("Fixture not yet implemented by SPEC task")


# =============================================================================
# TEST: Card Model (Task 001 verifies)
# =============================================================================

def test_card_model(app_components):
    """
    Card dataclass can be imported and has required fields.

    Required fields:
    - id: int (primary key)
    - front: str
    - back: str
    - next_review: date
    - interval: int

    SPEC task: Verify Card class has these attributes.
    BUILD task 001: Implement Card dataclass with fastlite.
    """
    app, db, Card = app_components

    # SPEC task fills in assertions:
    # - Check Card has required attributes
    # - Check default values if any
    pass


# =============================================================================
# TESTS: CRUD Routes (Task 002 verifies)
# =============================================================================

def test_card_creation(client, app_components):
    """
    POST /cards/new creates a card and redirects to /cards.

    Test flow:
    1. POST to /cards/new with form data (front, back)
    2. Assert redirect (303) to /cards
    3. GET /cards and verify new card appears

    SPEC task: Implement full test with assertions.
    BUILD task 002: Implement POST /cards/new route.
    """
    app, db, Card = app_components

    # SPEC task fills in:
    # response = client.post("/cards/new", data={"front": "Q", "back": "A"}, follow_redirects=False)
    # assert response.status_code == 303
    # ... verify card exists in /cards listing
    pass


def test_card_listing(client, db_with_card):
    """
    GET /cards shows all cards with their front text.

    Test flow:
    1. Use db_with_card fixture (has one card)
    2. GET /cards
    3. Assert response contains card's front text

    SPEC task: Implement assertions.
    BUILD task 002: Implement GET /cards route.
    """
    db, Card, card_id = db_with_card

    # SPEC task fills in:
    # response = client.get("/cards")
    # assert response.status_code == 200
    # assert "Test Question" in response.text
    pass


def test_card_deletion(client, db_with_card, app_components):
    """
    POST /cards/{id}/delete removes card and redirects.

    Test flow:
    1. Use db_with_card fixture (provides actual card_id)
    2. POST to /cards/{card_id}/delete  # Use card_id from fixture!
    3. Assert redirect (303) to /cards
    4. Verify card with that card_id no longer exists

    SPEC task: Implement assertions using card_id from fixture.
    BUILD task 002: Implement DELETE route.

    CRITICAL: Use card_id from db_with_card fixture. Do NOT assume id=1.
    """
    db, Card, card_id = db_with_card  # card_id is actual ID, may not be 1

    # SPEC task fills in:
    # response = client.post(f"/cards/{card_id}/delete", follow_redirects=False)
    # assert response.status_code == 303
    # Verify card is gone using card_id (NOT hardcoded 1):
    # assert db[Card].get(card_id) is None  # Or similar based on API
    pass


# =============================================================================
# TESTS: Study Routes (Task 003 verifies)
# =============================================================================

def test_study_shows_due(client, db_with_card):
    """
    GET /study shows cards that are due today or earlier.

    Test flow:
    1. db_with_card has card due today
    2. GET /study
    3. Assert card's front text is shown
    4. Assert "No cards due" is NOT shown

    Edge case: If no cards due, should show "No cards due" message.

    SPEC task: Implement assertions.
    BUILD task 003: Implement GET /study with due date filtering.
    """
    db, Card, card_id = db_with_card

    # SPEC task fills in:
    # response = client.get("/study")
    # assert response.status_code == 200
    # assert "Test Question" in response.text
    # assert "No cards due" not in response.text
    pass


def test_rating_updates_interval(client, db_with_card, app_components):
    """
    POST /study/{id}/rate applies SM-2 algorithm correctly.

    SM-2 ratings:
    - 0 (Again): interval = 1
    - 1 (Hard): interval = interval * 1.2
    - 2 (Good): interval = interval * 2.0
    - 3 (Easy): interval = interval * 3.0

    After rating: next_review = today + interval days

    Test flow:
    1. db_with_card has card with interval=1 (use card_id from fixture!)
    2. POST /study/{card_id}/rate with rating=2 (Good)
    3. Assert redirect to /study
    4. Verify interval is now 2 (1 * 2.0)
    5. Verify next_review is today + 2 days

    SPEC task: Implement full SM-2 test using card_id from fixture.
    BUILD task 003: Implement rating route with SM-2 logic.

    CRITICAL: Use card_id from db_with_card fixture. Do NOT assume id=1.
    """
    db, Card, card_id = db_with_card  # card_id is actual ID, may not be 1
    app, _, _ = app_components

    # SPEC task fills in:
    # response = client.post(f"/study/{card_id}/rate", data={"rating": "2"}, follow_redirects=False)
    # assert response.status_code == 303
    #
    # # Verify interval updated using card_id (NOT hardcoded 1):
    # card = db[Card][card_id]  # Or similar based on API
    # assert card.interval == 2
    # assert card.next_review == date.today() + timedelta(days=2)
    pass
