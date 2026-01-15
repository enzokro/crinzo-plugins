"""FTL v2 Test Fixtures."""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def lib_path():
    """Return path to FTL lib directory."""
    return Path(__file__).resolve().parent.parent / "lib"


@pytest.fixture
def ftl_dir(tmp_path):
    """Create a temporary .ftl directory structure."""
    ftl = tmp_path / ".ftl"
    (ftl / "workspace").mkdir(parents=True)
    (ftl / "cache").mkdir(parents=True)
    yield tmp_path
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def memory_module(lib_path):
    """Import and return memory module."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import memory
    importlib.reload(memory)  # Fresh import
    return memory


@pytest.fixture
def workspace_module(lib_path):
    """Import and return workspace module."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import workspace
    importlib.reload(workspace)
    return workspace


@pytest.fixture
def campaign_module(lib_path):
    """Import and return campaign module."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import campaign
    importlib.reload(campaign)
    return campaign


class CLIRunner:
    """Run FTL CLI commands in a temp directory."""

    def __init__(self, lib_path: Path, work_dir: Path):
        self.lib_path = lib_path
        self.work_dir = work_dir

    def run(self, module: str, *args, stdin: str = None) -> tuple[int, str, str]:
        """Run a lib module with args. Returns (code, stdout, stderr)."""
        cmd = ["python3", str(self.lib_path / f"{module}.py")] + list(args)
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            input=stdin
        )
        return result.returncode, result.stdout, result.stderr

    def memory(self, *args, stdin: str = None):
        return self.run("memory", *args, stdin=stdin)

    def workspace(self, *args, stdin: str = None):
        return self.run("workspace", *args, stdin=stdin)

    def campaign(self, *args, stdin: str = None):
        return self.run("campaign", *args, stdin=stdin)

    def exploration(self, *args, stdin: str = None):
        return self.run("exploration", *args, stdin=stdin)


@pytest.fixture
def cli(lib_path, ftl_dir):
    """Create CLI runner for testing."""
    return CLIRunner(lib_path, ftl_dir)


@pytest.fixture
def sample_plan():
    """Sample plan.json for testing."""
    return {
        "campaign": "test-campaign",
        "framework": "none",
        "idioms": {"required": [], "forbidden": []},
        "tasks": [
            {
                "seq": "001",
                "slug": "first-task",
                "type": "SPEC",
                "delta": ["test_file.py"],
                "verify": "pytest test_file.py --collect-only",
                "budget": 3,
                "depends": "none"
            },
            {
                "seq": "002",
                "slug": "second-task",
                "type": "BUILD",
                "delta": ["main.py"],
                "verify": "pytest -v",
                "budget": 5,
                "depends": "001",
                "preflight": ["python -m py_compile main.py"]
            }
        ]
    }


@pytest.fixture
def sample_plan_with_framework():
    """Sample plan.json with framework idioms."""
    return {
        "campaign": "fasthtml-app",
        "framework": "FastHTML",
        "idioms": {
            "required": ["Use @rt decorator", "Return component trees"],
            "forbidden": ["Raw HTML strings"]
        },
        "tasks": [
            {
                "seq": "001",
                "slug": "add-route",
                "type": "BUILD",
                "delta": ["main.py"],
                "verify": "python -c 'import main'",
                "budget": 5,
                "depends": "none"
            }
        ]
    }
