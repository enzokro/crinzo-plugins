"""Tests for tasks.py - builder output parsing.

Tests the parsing of builder output format (DELIVERED/BLOCKED).
"""

import pytest


class TestParseOutput:
    """Tests for parse_builder_output function."""

    def test_parse_delivered(self):
        """Parses DELIVERED output correctly."""
        from lib.tasks import parse_builder_output

        output = """
Some log output here...
Building module...
DELIVERED: Implemented JWT authentication with refresh token support
Done.
"""

        result = parse_builder_output(output)

        assert result["status"] == "delivered"
        assert "JWT authentication" in result["summary"]
        assert result["tried"] == ""
        assert result["error"] == ""

    def test_parse_blocked(self):
        """Parses BLOCKED output correctly."""
        from lib.tasks import parse_builder_output

        output = """
Attempting to implement...
BLOCKED: Cannot proceed due to circular import between auth and user modules
TRIED: Moved shared types to separate module
ERROR: ImportError: cannot import name 'User' from 'auth'
"""

        result = parse_builder_output(output)

        assert result["status"] == "blocked"
        assert "circular import" in result["summary"]
        assert "shared types" in result["tried"]
        assert "ImportError" in result["error"]

    def test_parse_with_tried_error(self):
        """Extracts TRIED and ERROR fields."""
        from lib.tasks import parse_builder_output

        output = """
BLOCKED: Database schema migration failed
TRIED: Applied migration with alembic upgrade head
ERROR: sqlalchemy.exc.OperationalError: table already exists
"""

        result = parse_builder_output(output)

        assert result["status"] == "blocked"
        assert result["tried"] != ""
        assert result["error"] != ""
        assert "alembic" in result["tried"]
        assert "OperationalError" in result["error"]

    def test_parse_unknown(self):
        """Returns unknown status when no markers found."""
        from lib.tasks import parse_builder_output

        output = """
Some random output
Without any status markers
Just logging stuff
"""

        result = parse_builder_output(output)

        assert result["status"] == "unknown"
        assert result["summary"] == ""
