"""FTL v2 Test Fixtures with Database Support."""

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
def ftl_dir(tmp_path, monkeypatch):
    """Create a temporary .ftl directory structure with isolated database."""
    ftl = tmp_path / ".ftl"
    (ftl / "workspace").mkdir(parents=True)
    (ftl / "cache").mkdir(parents=True)

    # Change to tmp directory so .ftl/ftl.db is created there
    monkeypatch.chdir(tmp_path)

    yield tmp_path
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def test_db(ftl_dir, lib_path, monkeypatch):
    """Isolated database for each test.

    This fixture:
    1. Changes to tmp directory (via ftl_dir)
    2. Resets the database singleton
    3. Initializes fresh database
    4. Yields the database connection
    5. Cleans up after test
    """
    # Add lib to path
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))

    # Import and reset connection
    from db import connection
    from db import init_db, get_db, reset_db

    # Reset singleton to force new connection
    connection._db = None
    connection.DB_PATH = ftl_dir / ".ftl" / "ftl.db"

    # Initialize fresh database
    init_db()
    db = get_db()

    yield db

    # Cleanup
    reset_db()


@pytest.fixture
def memory_module(lib_path, test_db):
    """Import and return memory module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import memory
    importlib.reload(memory)
    return memory


@pytest.fixture
def workspace_module(lib_path, test_db):
    """Import and return workspace module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import workspace
    importlib.reload(workspace)
    return workspace


@pytest.fixture
def campaign_module(lib_path, test_db):
    """Import and return campaign module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import campaign
    importlib.reload(campaign)
    return campaign


@pytest.fixture
def exploration_module(lib_path, test_db):
    """Import and return exploration module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import exploration
    importlib.reload(exploration)
    return exploration


@pytest.fixture
def phase_module(lib_path, test_db):
    """Import and return phase module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import phase
    importlib.reload(phase)
    return phase


@pytest.fixture
def plan_module(lib_path, test_db):
    """Import and return plan module with fresh database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    import importlib
    import plan
    importlib.reload(plan)
    return plan


class CLIRunner:
    """Run FTL CLI commands in a temp directory."""

    def __init__(self, lib_path: Path, work_dir: Path):
        self.lib_path = lib_path
        self.work_dir = work_dir

    def run(self, module: str, *args, stdin: str = None) -> tuple:
        """Run a lib module with args. Returns (code, stdout, stderr)."""
        cmd = [sys.executable, str(self.lib_path / f"{module}.py")] + list(args)
        env = os.environ.copy()
        env['FTL_DB_PATH'] = str(self.work_dir / ".ftl" / "ftl.db")
        result = subprocess.run(
            cmd,
            cwd=self.work_dir,
            capture_output=True,
            text=True,
            input=stdin,
            env=env
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

    def phase(self, *args, stdin: str = None):
        return self.run("phase", *args, stdin=stdin)

    def plan(self, *args, stdin: str = None):
        return self.run("plan", *args, stdin=stdin)

    def create_plan(self, plan_dict: dict) -> int:
        """Store plan in database and return ID."""
        code, out, _ = self.plan("write", stdin=json.dumps(plan_dict))
        if code != 0:
            raise RuntimeError(f"Failed to create plan: {out}")
        return json.loads(out)["id"]


@pytest.fixture
def cli(lib_path, ftl_dir, test_db):
    """Create CLI runner for testing.

    Depends on test_db to ensure database isolation.
    """
    return CLIRunner(lib_path, ftl_dir)


@pytest.fixture
def sample_plan():
    """Sample plan.json for testing."""
    return {
        "objective": "Test objective",
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
        "objective": "Build FastHTML app",
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


@pytest.fixture
def sample_dag_plan():
    """Sample plan.json with DAG dependencies (multi-parent)."""
    return {
        "objective": "Build with DAG dependencies",
        "campaign": "dag-campaign",
        "framework": "none",
        "idioms": {"required": [], "forbidden": []},
        "tasks": [
            {
                "seq": "001",
                "slug": "spec-auth",
                "type": "SPEC",
                "delta": ["tests/test_auth.py"],
                "verify": "pytest --collect-only tests/test_auth.py",
                "budget": 3,
                "depends": "none"
            },
            {
                "seq": "002",
                "slug": "spec-api",
                "type": "SPEC",
                "delta": ["tests/test_api.py"],
                "verify": "pytest --collect-only tests/test_api.py",
                "budget": 3,
                "depends": "none"
            },
            {
                "seq": "003",
                "slug": "impl-auth",
                "type": "BUILD",
                "delta": ["lib/auth.py"],
                "verify": "pytest tests/test_auth.py",
                "budget": 5,
                "depends": "001"
            },
            {
                "seq": "004",
                "slug": "impl-api",
                "type": "BUILD",
                "delta": ["lib/api.py"],
                "verify": "pytest tests/test_api.py",
                "budget": 5,
                "depends": "002"
            },
            {
                "seq": "005",
                "slug": "integrate",
                "type": "BUILD",
                "delta": ["lib/main.py"],
                "verify": "pytest tests/",
                "budget": 5,
                "depends": ["003", "004"]  # Multi-parent dependency
            }
        ]
    }


@pytest.fixture
def sample_failure():
    """Sample failure entry for testing."""
    return {
        "name": "import-module-error",
        "trigger": "ModuleNotFoundError: No module named 'fastsql'",
        "fix": "pip install fastsql",
        "cost": 500,
        "source": ["test-workspace-001"]
    }


@pytest.fixture
def sample_pattern():
    """Sample pattern entry for testing."""
    return {
        "name": "fasthtml-route-pattern",
        "trigger": "Adding new route to FastHTML app",
        "insight": "Use @rt decorator and return component trees",
        "saved": 1000,
        "source": ["test-workspace-002"]
    }


@pytest.fixture
def active_campaign(cli, sample_plan):
    """Create an active campaign for workspace tests."""
    code, out, err = cli.campaign("create", sample_plan["objective"])
    assert code == 0, f"Failed to create campaign: {err}"
    return json.loads(out)


@pytest.fixture
def create_workspace(test_db, lib_path):
    """Factory fixture to create test workspaces in database."""
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))
    from db.schema import Workspace
    from datetime import datetime

    def _create(workspace_id, status="active", campaign_id=1, **kwargs):
        parts = workspace_id.split("-")
        seq = parts[0]
        slug = "-".join(parts[1:]) if len(parts) > 1 else workspace_id
        now = datetime.now().isoformat()

        ws = Workspace(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            seq=seq,
            slug=slug,
            status=status,
            created_at=now,
            completed_at=now if status == "complete" else None,
            blocked_at=now if status == "blocked" else None,
            objective=kwargs.get("objective", "Test objective"),
            delta=json.dumps(kwargs.get("delta", [])),
            verify=kwargs.get("verify", "pytest"),
            budget=kwargs.get("budget", 5),
            delivered=kwargs.get("delivered", "")
        )
        test_db.t.workspace.insert(ws)
        return ws

    return _create
