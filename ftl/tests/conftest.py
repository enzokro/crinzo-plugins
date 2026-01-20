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

    # Create common delta files used by sample_plan fixtures
    # These must exist for workspace.create() validation
    (tmp_path / "test_file.py").write_text("# Test file\n")
    (tmp_path / "main.py").write_text("# Main file\n")
    (tmp_path / "a.py").write_text("# A file\n")
    (tmp_path / "b.py").write_text("# B file\n")

    # Create nested paths for more complex test plans
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "tests" / "test_auth.py").write_text("# Auth tests\n")
    (tmp_path / "tests" / "test_api.py").write_text("# API tests\n")
    (tmp_path / "lib").mkdir(exist_ok=True)
    (tmp_path / "lib" / "auth.py").write_text("# Auth lib\n")
    (tmp_path / "lib" / "api.py").write_text("# API lib\n")
    (tmp_path / "lib" / "main.py").write_text("# Main lib\n")

    # Change to tmp directory so .ftl/ftl.db is created there
    monkeypatch.chdir(tmp_path)

    yield tmp_path
    # Cleanup handled by tmp_path fixture


@pytest.fixture
def test_db(ftl_dir, lib_path, monkeypatch):
    """Isolated database for each test.

    This fixture:
    1. Changes to tmp directory (via ftl_dir)
    2. Closes any existing database connection
    3. Sets database path to test-specific location
    4. Initializes fresh database
    5. Yields the database connection
    6. Cleans up after test
    """
    # Add lib to path
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))

    from db import connection
    from db import init_db, get_db, reset_db

    # Close existing connection and set path for this test
    connection._db = None
    connection.DB_PATH = ftl_dir / ".ftl" / "ftl.db"

    # Initialize fresh database
    init_db()
    db = get_db()

    yield db

    # Cleanup: close connection and delete database file
    reset_db()


def _reload_module_with_fresh_db(lib_path, module_name, db_path):
    """Reload a module ensuring it uses the correct database.

    Ensures db.connection points to the test's database path,
    then reloads the target module to pick up fresh state.

    IMPORTANT: We must ensure both the test and the reloaded module use
    the SAME db.connection module. Python can load the same module under
    different paths (e.g., 'db' vs 'lib.db'), creating separate singletons.

    Args:
        lib_path: Path to lib directory
        module_name: Name of module to reload
        db_path: Database path for this test
    """
    if str(lib_path) not in sys.path:
        sys.path.insert(0, str(lib_path))

    import importlib
    from db import connection

    # Reset connection state and set path
    connection._db = None
    connection.DB_PATH = db_path

    # CRITICAL: Also update lib.db.connection if it exists as a separate module.
    # Modules can be loaded under both 'db' and 'lib.db' paths, creating
    # separate singletons. We must sync them.
    if 'lib.db' in sys.modules:
        lib_db = sys.modules['lib.db']
        if hasattr(lib_db, 'connection'):
            lib_db.connection._db = None
            lib_db.connection.DB_PATH = db_path
    if 'lib.db.connection' in sys.modules:
        lib_db_conn = sys.modules['lib.db.connection']
        lib_db_conn._db = None
        lib_db_conn.DB_PATH = db_path

    # Now reload the target module
    module = importlib.import_module(module_name)
    importlib.reload(module)
    return module


@pytest.fixture
def memory_module(lib_path, test_db, ftl_dir):
    """Import and return memory module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "memory", db_path)


@pytest.fixture
def workspace_module(lib_path, test_db, ftl_dir):
    """Import and return workspace module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "workspace", db_path)


@pytest.fixture
def campaign_module(lib_path, test_db, ftl_dir):
    """Import and return campaign module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "campaign", db_path)


@pytest.fixture
def exploration_module(lib_path, test_db, ftl_dir):
    """Import and return exploration module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "exploration", db_path)


@pytest.fixture
def phase_module(lib_path, test_db, ftl_dir):
    """Import and return phase module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    module = _reload_module_with_fresh_db(lib_path, "phase", db_path)
    # Reset state to ensure clean state for each test
    module.reset()
    return module


@pytest.fixture
def plan_module(lib_path, test_db, ftl_dir):
    """Import and return plan module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "plan", db_path)


@pytest.fixture
def orchestration_module(lib_path, test_db, ftl_dir):
    """Import and return orchestration module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "orchestration", db_path)


@pytest.fixture
def decision_parser_module(lib_path, test_db, ftl_dir):
    """Import and return decision_parser module with fresh database."""
    db_path = ftl_dir / ".ftl" / "ftl.db"
    return _reload_module_with_fresh_db(lib_path, "decision_parser", db_path)


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
