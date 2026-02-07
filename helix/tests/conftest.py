"""Shared fixtures for helix test suite.

Design principles:
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

    Provides clean directory for state persistence tests.
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
