"""Shared fixtures for helix test suite.

Design principles (from FTL patterns):
- Database isolation: Fresh DB per test via fixture
- Module reloading: Reset singleton connections
- Sample data factories: Reusable test data
- No mocking core logic: Test real SQLite operations
"""

import os
import sys
import pytest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timedelta

# Ensure helix lib is importable
sys.path.insert(0, str(Path(__file__).parent.parent))


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
def sample_memories(test_db):
    """Pre-populated memories for recall tests.

    Creates a mix of failure and pattern memories with varying
    effectiveness for testing recall ranking.
    """
    from lib.memory.core import store

    memories = [
        {
            "trigger": "Import error when using relative imports in src/auth/jwt.py",
            "resolution": "Use absolute imports from package root: from auth.jwt import create_token",
            "type": "failure",
            "source": "test_fixture"
        },
        {
            "trigger": "Database connection timeout in production environment",
            "resolution": "Add retry logic with exponential backoff, check connection pool settings",
            "type": "failure",
            "source": "test_fixture"
        },
        {
            "trigger": "Task: implement user authentication endpoint",
            "resolution": "Use JWT tokens, store refresh tokens in httponly cookies, validate on each request",
            "type": "pattern",
            "source": "test_fixture"
        },
        {
            "trigger": "Test failures when mocking external APIs for payment service",
            "resolution": "Use dependency injection pattern, mock at service boundary not HTTP level",
            "type": "failure",
            "source": "test_fixture"
        },
        {
            "trigger": "Task: optimize database queries for dashboard metrics",
            "resolution": "Add composite indexes, use query batching, implement caching layer",
            "type": "pattern",
            "source": "test_fixture"
        },
    ]

    stored = []
    for m in memories:
        result = store(**m)
        stored.append({**m, "name": result["name"], "status": result["status"]})

    return stored


@pytest.fixture
def mock_embeddings(monkeypatch):
    """Deterministic embeddings for testing.

    Replaces sentence-transformers with predictable embeddings
    based on text hash, enabling reliable similarity tests.
    """
    import hashlib

    def deterministic_embed(text):
        """Generate deterministic 384-dim embedding from text hash."""
        h = hashlib.sha256(text.encode()).digest()
        # Expand hash to 384 dimensions (deterministic pseudo-random)
        embedding = []
        for i in range(384):
            byte_idx = i % 32
            embedding.append((h[byte_idx] + i) / 255.0 - 0.5)
        return embedding

    def mock_to_blob(emb):
        import struct
        return struct.pack(f'{len(emb)}f', *emb)

    def mock_from_blob(blob):
        import struct
        count = len(blob) // 4
        return list(struct.unpack(f'{count}f', blob))

    def mock_cosine(a, b):
        import math
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # Patch embeddings module
    from lib.memory import embeddings
    monkeypatch.setattr(embeddings, "embed", deterministic_embed)
    monkeypatch.setattr(embeddings, "to_blob", mock_to_blob)
    monkeypatch.setattr(embeddings, "from_blob", mock_from_blob)
    monkeypatch.setattr(embeddings, "cosine", mock_cosine)

    return {
        "embed": deterministic_embed,
        "cosine": mock_cosine,
    }


@pytest.fixture
def meta_dir(tmp_path, monkeypatch):
    """Isolated .helix directory for meta state.

    Provides clean directory for OrchestratorMeta persistence tests.
    """
    helix_dir = tmp_path / ".helix"
    helix_dir.mkdir()

    # Patch cwd to use tmp_path
    monkeypatch.chdir(tmp_path)

    return helix_dir


@pytest.fixture
def sample_task_data():
    """Sample task data for context building tests."""
    return {
        "id": "task-001",
        "subject": "001: impl-user-auth",
        "description": "Implement user authentication with JWT tokens",
        "metadata": {
            "verify": "pytest tests/test_auth.py -v",
            "framework": "pytest",
            "relevant_files": ["src/auth/jwt.py", "src/routes/auth.py"],
            "delta": ["src/auth/jwt.py"]
        }
    }


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
    """Task list with blocked tasks for stall detection tests."""
    return [
        {
            "id": "task-001",
            "subject": "001: setup-db",
            "status": "completed",
            "blockedBy": [],
            "metadata": {"helix_outcome": "delivered"}
        },
        {
            "id": "task-002",
            "subject": "002: impl-models",
            "status": "completed",
            "blockedBy": ["task-001"],
            "metadata": {"helix_outcome": "blocked", "blocked_reason": "schema conflict"}
        },
        {
            "id": "task-003",
            "subject": "003: impl-auth",
            "status": "pending",
            "blockedBy": ["task-002"],
            "metadata": {}
        },
    ]
