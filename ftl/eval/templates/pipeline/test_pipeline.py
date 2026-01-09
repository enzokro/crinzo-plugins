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
def pipeline_module():
    """Deferred import - allows test collection before implementation exists."""
    try:
        from pipeline import parse_csv, validate_record, transform_employee, aggregate_by_department, generate_report
        return parse_csv, validate_record, transform_employee, aggregate_by_department, generate_report
    except ImportError:
        pytest.skip("pipeline.py not yet implemented")


@pytest.fixture
def sample_csv_path(tmp_path):
    """Create a sample CSV file for testing."""
    pytest.skip("Fixture not yet implemented by SPEC task")


@pytest.fixture
def sample_record():
    """Create a sample record dict for testing."""
    pytest.skip("Fixture not yet implemented by SPEC task")


# =============================================================================
# TESTS: Parse + Validate (Task 001 verifies)
# =============================================================================

def test_parse_csv_record_count(pipeline_module, sample_csv_path):
    """CSV parsing produces correct record count."""
    pass


def test_validate_invalid_email(pipeline_module, sample_record):
    """Invalid email is rejected with error."""
    pass


def test_validate_negative_age(pipeline_module, sample_record):
    """Negative age is rejected with error."""
    pass


def test_validate_empty_email(pipeline_module, sample_record):
    """Empty email is rejected with error."""
    pass


# =============================================================================
# TESTS: Transform (Task 002 verifies)
# =============================================================================

def test_transform_name_titlecase(pipeline_module, sample_record):
    """Name normalization works (title case)."""
    pass


# =============================================================================
# TESTS: Aggregate + Report (Task 003 verifies)
# =============================================================================

def test_aggregate_department_counts(pipeline_module):
    """Department aggregation produces correct counts."""
    pass


def test_aggregate_average_calculations(pipeline_module):
    """Average calculations are accurate."""
    pass


def test_report_structure(pipeline_module):
    """Final report matches expected structure."""
    pass
