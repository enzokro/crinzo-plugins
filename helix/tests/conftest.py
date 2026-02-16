"""Shared fixtures for helix test suite.

Design principles:
- Database isolation: Fresh DB per test via fixture
- Module reloading: Reset singleton connections
- Sample data factories: Reusable test data
- No mocking core logic: Test real SQLite operations
"""

import sys
import pytest
from pathlib import Path

# Ensure helix lib is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _reset_session_tracking():
    """Reset injection session tracking between tests to prevent cross-test leakage."""
    from lib.injection import reset_session_tracking
    reset_session_tracking()
    yield
    reset_session_tracking()


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    """Fresh in-memory SQLite database per test.

    Isolates each test with its own database, preventing state leakage.
    Monkeypatches DB_PATH and resets singleton connection after test.
    """
    db_path = tmp_path / "test_helix.db"
    monkeypatch.setenv("HELIX_DB_PATH", str(db_path))

    # Reset any existing singleton
    from lib.db import connection
    connection.reset_db()
    connection.DB_PATH = str(db_path)

    # Initialize fresh
    db = connection.get_db()
    connection.init_db(db)

    yield db

    # Cleanup
    connection.reset_db()


@pytest.fixture
def sample_insights(test_db, mock_embeddings):
    """Pre-populated insights for recall tests.

    Creates a mix of insights with varying effectiveness
    for testing recall ranking.
    """
    from lib.memory.core import store

    insights = [
        {
            "content": "When importing fails in Python, check sys.path first because module resolution depends on it",
            "tags": ["python", "debugging"]
        },
        {
            "content": "When database connection times out, add retry with exponential backoff because transient failures are common",
            "tags": ["database", "reliability"]
        },
        {
            "content": "When implementing auth, use JWT with refresh tokens stored in httponly cookies for security",
            "tags": ["auth", "security"]
        },
        {
            "content": "When mocking external APIs, mock at service boundary not HTTP level for better isolation",
            "tags": ["testing", "mocking"]
        },
        {
            "content": "When optimizing queries, add composite indexes and use query batching for performance",
            "tags": ["database", "performance"]
        },
    ]

    stored = []
    for i in insights:
        result = store(**i)
        stored.append({**i, "name": result["name"], "status": result["status"]})

    return stored


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Deterministic embeddings for testing.

    Replaces sentence-transformers with predictable embeddings
    based on text hash, enabling reliable similarity tests.
    """
    import hashlib

    def deterministic_embed(text, is_query=False):
        """Generate deterministic 256-dim embedding from text hash."""
        h = hashlib.sha256(text.encode()).digest()
        # Expand hash to 256 dimensions (deterministic pseudo-random)
        embedding = []
        for i in range(256):
            byte_idx = i % 32
            embedding.append((h[byte_idx] + i) / 255.0 - 0.5)
        return embedding

    # Patch embeddings module — only embed needs mocking.
    # to_blob is trivial struct pack and doesn't need replacement.
    from lib.memory import embeddings
    monkeypatch.setattr(embeddings, "embed", deterministic_embed)

    return {
        "embed": deterministic_embed,
    }


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Isolated database without mock embeddings — for tests needing real semantic similarity.

    Unlike test_db, this does NOT mock embeddings, allowing tests to validate
    actual embedding behavior (relevance gate, causal filtering, etc.).
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("HELIX_DB_PATH", db_path)

    from lib.db import connection as conn_module
    conn_module.DB_PATH = db_path
    conn_module.reset_db()

    yield db_path

    conn_module.reset_db()


@pytest.fixture
def isolated_env(isolated_db, tmp_path, monkeypatch):
    """Isolated database + .helix directory — for hook integration tests needing real embeddings.

    Composes with isolated_db; adds HELIX_PROJECT_DIR and .helix directory.
    """
    monkeypatch.setenv("HELIX_PROJECT_DIR", str(tmp_path))

    helix_dir = tmp_path / ".helix"
    helix_dir.mkdir(exist_ok=True)

    yield tmp_path


@pytest.fixture
def sample_tasks():
    """Sample task list for orchestrator tests."""
    return [
        {
            "id": "task-001",
            "subject": "001: setup-db",
            "status": "completed",
            "blockedBy": [],
            "metadata": {"helix_outcome": "delivered", "delivered_summary": "Created schema"}
        },
        {
            "id": "task-002",
            "subject": "002: impl-models",
            "status": "completed",
            "blockedBy": ["task-001"],
            "metadata": {"helix_outcome": "delivered", "delivered_summary": "User model added"}
        },
        {
            "id": "task-003",
            "subject": "003: impl-auth",
            "status": "pending",
            "blockedBy": ["task-002"],
            "metadata": {}
        },
        {
            "id": "task-004",
            "subject": "004: impl-api",
            "status": "pending",
            "blockedBy": ["task-003"],
            "metadata": {}
        },
    ]


@pytest.fixture
def sample_tasks_with_blocked():
    """Task list with a blocked blocker - creates stall scenario.

    task-001: completed (delivered)
    task-002: completed but BLOCKED (not delivered)
    task-003: pending, depends on task-002 (cannot run due to blocked blocker)
    """
    return [
        {
            "id": "task-001",
            "subject": "001: setup-db",
            "status": "completed",
            "blockedBy": [],
            "metadata": {"helix_outcome": "delivered", "delivered_summary": "Created schema"}
        },
        {
            "id": "task-002",
            "subject": "002: impl-models",
            "status": "completed",
            "blockedBy": ["task-001"],
            "metadata": {"helix_outcome": "blocked", "blocked_reason": "Schema incompatible"}
        },
        {
            "id": "task-003",
            "subject": "003: impl-auth",
            "status": "pending",
            "blockedBy": ["task-002"],
            "metadata": {}
        },
    ]
