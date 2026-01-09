"""
Test Suite Scaffold

SPEC task fills in assertions. BUILD tasks implement to pass them.
BUILD tasks MAY adjust assertions if the behavioral CONTRACT is preserved.
"""
import pytest


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def parser_module():
    """Deferred import - allows test collection before implementation exists."""
    try:
        from parser import parse_config, ConfigError
        return parse_config, ConfigError
    except ImportError:
        pytest.skip("parser.py not yet implemented")


@pytest.fixture
def valid_config_path(tmp_path):
    """Create a valid TOML config file for testing."""
    pytest.skip("Fixture not yet implemented by SPEC task")


@pytest.fixture
def invalid_config_path(tmp_path):
    """Create an invalid TOML config file for testing."""
    pytest.skip("Fixture not yet implemented by SPEC task")


# =============================================================================
# TEST: Dataclasses (Task 001 verifies)
# =============================================================================

def test_dataclass_exists(parser_module):
    """Config dataclasses can be imported."""
    pass


# =============================================================================
# TESTS: Valid Config (Task 002 verifies)
# =============================================================================

def test_valid_config_parses(parser_module, valid_config_path):
    """parse_config returns Config for valid TOML."""
    pass


# =============================================================================
# TESTS: Validation Errors (Task 003 verifies)
# =============================================================================

def test_error_type_string_for_integer(parser_module, invalid_config_path):
    """Type error detected: string instead of integer."""
    pass


def test_error_range_port(parser_module, invalid_config_path):
    """Range error detected: port > 65535."""
    pass


def test_error_range_negative_timeout(parser_module, invalid_config_path):
    """Range error detected: negative timeout."""
    pass


def test_error_cross_field_ssl(parser_module, invalid_config_path):
    """Cross-field error: ssl=true without cert_path."""
    pass


def test_error_message_format(parser_module, invalid_config_path):
    """Error message format matches specification."""
    pass


def test_error_line_numbers(parser_module, invalid_config_path):
    """Line numbers in errors are accurate."""
    pass


def test_error_multiple_collected(parser_module, invalid_config_path):
    """Multiple errors collected (not fail-fast)."""
    pass
