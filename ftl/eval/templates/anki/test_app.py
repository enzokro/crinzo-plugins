"""
Test Suite Scaffold

SPEC task fills in assertions. BUILD tasks implement to pass them.
BUILD tasks MAY adjust assertions if the behavioral CONTRACT is preserved.

## Relative Assertions

Use values from fixtures, not hardcoded assumptions.
"""
import pytest
from datetime import date, timedelta


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def app_components():
    """Deferred import - allows test collection before implementation exists."""
    try:
        from main import app, db, Card
        return app, db, Card
    except ImportError:
        pytest.skip("main.py not yet implemented")


@pytest.fixture
def client(app_components):
    """Test client for HTTP requests."""
    from starlette.testclient import TestClient
    app, db, Card = app_components
    return TestClient(app)


@pytest.fixture
def db_with_card(app_components):
    """
    Database with one test record inserted.

    Returns tuple: (db, Model, record_id)

    SPEC task: implement insertion and return actual ID from fixture.
    """
    app, db, Card = app_components
    pytest.skip("Fixture not yet implemented by SPEC task")


# =============================================================================
# TEST: Card Model (Task 001 verifies)
# =============================================================================

def test_card_model(app_components):
    """Card dataclass has required fields: id, front, back, next_review, interval."""
    app, db, Card = app_components
    pass


# =============================================================================
# TESTS: CRUD Routes (Task 002 verifies)
# =============================================================================

def test_card_creation(client, app_components):
    """POST /cards/new creates a card and redirects."""
    app, db, Card = app_components
    pass


def test_card_listing(client, db_with_card):
    """GET /cards shows all cards."""
    db, Card, card_id = db_with_card
    pass


def test_card_deletion(client, db_with_card, app_components):
    """
    POST /cards/{id}/delete removes card and redirects.

    SPEC task: Use card_id from fixture, verify deletion.
    """
    db, Card, card_id = db_with_card
    pass


# =============================================================================
# TESTS: Study Routes (Task 003 verifies)
# =============================================================================

def test_study_shows_due(client, db_with_card):
    """GET /study shows cards due today or earlier."""
    db, Card, card_id = db_with_card
    pass


def test_rating_updates_interval(client, db_with_card, app_components):
    """
    POST /study/{id}/rate applies SM-2 algorithm correctly.

    SPEC task: Use card_id from fixture, verify interval update.
    """
    db, Card, card_id = db_with_card
    app, _, _ = app_components
    pass
