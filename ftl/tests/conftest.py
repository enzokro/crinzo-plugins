"""Pytest fixtures for FTL tests."""

import os
import subprocess
import tempfile
import shutil
import pytest
from pathlib import Path


@pytest.fixture
def lib_path():
    """Return path to FTL lib directory."""
    return Path(__file__).resolve().parent.parent / "lib"


@pytest.fixture
def tmpdir():
    """Create a temporary directory with FTL structure."""
    tmpdir = tempfile.mkdtemp(prefix="ftl_test_")
    os.makedirs(f"{tmpdir}/.ftl/campaigns/active", exist_ok=True)
    os.makedirs(f"{tmpdir}/.ftl/campaigns/complete", exist_ok=True)
    os.makedirs(f"{tmpdir}/.ftl/workspace", exist_ok=True)
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


class TestFixture:
    """Test fixture with temp directory and FTL structure."""

    def __init__(self, lib_path):
        self.lib_path = lib_path
        self.tmpdir = None

    def setup(self):
        """Create temp directory with FTL structure."""
        self.tmpdir = tempfile.mkdtemp(prefix="ftl_cli_test_")
        os.makedirs(f"{self.tmpdir}/.ftl/campaigns/active", exist_ok=True)
        os.makedirs(f"{self.tmpdir}/.ftl/campaigns/complete", exist_ok=True)
        os.makedirs(f"{self.tmpdir}/.ftl/workspace", exist_ok=True)
        os.makedirs(f"{self.tmpdir}/.ftl/memory", exist_ok=True)
        return self.tmpdir

    def teardown(self):
        """Clean up temp directory."""
        if self.tmpdir:
            shutil.rmtree(self.tmpdir, ignore_errors=True)

    def cmd(self, subcmd, stdin=None):
        """Run campaign.py subcommand."""
        result = subprocess.run(
            f'python3 "{self.lib_path}/campaign.py" -b {self.tmpdir} {subcmd}',
            shell=True, capture_output=True, text=True, input=stdin
        )
        return result.returncode, result.stdout, result.stderr


@pytest.fixture
def fixture(lib_path):
    """Create TestFixture instance for CLI contract tests."""
    f = TestFixture(lib_path)
    f.setup()
    yield f
    f.teardown()


@pytest.fixture
def parse(lib_path):
    """Import and return parse_planner_output function."""
    import sys
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    from campaign import parse_planner_output
    return parse_planner_output


@pytest.fixture
def parse_filename(lib_path):
    """Import and return parse_workspace_filename function."""
    import sys
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    from memory import parse_workspace_filename
    return parse_workspace_filename


@pytest.fixture
def memory_module(lib_path):
    """Import and return memory module."""
    import sys
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import memory
    return memory
