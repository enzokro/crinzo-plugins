#!/usr/bin/env python3
"""Test FTL memory.py decision functions.

Validates decision index operations:
- mine_workspace: Build index from workspace files
- query_decisions: Search decisions by topic
- get_decision: Retrieve single decision
- get_lineage: Get ancestry chain
- trace_tag: Find decisions using tag
- impact_file: Find decisions affecting file
- find_stale: Find old decisions
- add_signal: Add +/- signal to failures/discoveries

Usage:
    python3 test_memory_decisions.py
    FTL_LIB=/path/to/lib python3 test_memory_decisions.py
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def get_lib_path():
    """Get FTL_LIB path from env or config."""
    lib_path = os.environ.get("FTL_LIB")
    if not lib_path:
        result = subprocess.run(
            "source ~/.config/ftl/paths.sh 2>/dev/null && echo $FTL_LIB",
            shell=True, capture_output=True, text=True
        )
        lib_path = result.stdout.strip()
    return lib_path


def import_memory(lib_path):
    """Import memory module."""
    sys.path.insert(0, lib_path)
    import memory
    return memory


class TestFixture:
    """Test fixture with temp directory and FTL structure."""

    def __init__(self, memory_module):
        self.memory = memory_module
        self.tmpdir = None

    def setup(self):
        """Create temp directory with FTL structure and sample workspaces."""
        self.tmpdir = Path(tempfile.mkdtemp(prefix="ftl_memory_test_"))
        workspace_dir = self.tmpdir / ".ftl" / "workspace"
        workspace_dir.mkdir(parents=True, exist_ok=True)

        # Create sample workspace files
        self._create_workspace(workspace_dir, "001", "setup-auth", "complete", None,
                               ["src/auth.py"], "Implemented auth module",
                               ["#pattern/session-token"])
        self._create_workspace(workspace_dir, "002", "add-login", "complete", "001",
                               ["src/auth.py", "src/routes.py"], "Added login route",
                               ["#pattern/session-token", "#constraint/no-plaintext"])
        self._create_workspace(workspace_dir, "003", "add-logout", "active", "002",
                               ["src/routes.py"], "", [])
        self._create_workspace(workspace_dir, "004", "fix-session", "blocked", "002",
                               ["src/session.py"], "BLOCKED: circular import",
                               ["#failure/circular-import"])

        return self.tmpdir

    def _create_workspace(self, workspace_dir, seq, slug, status, parent,
                          delta_files, delivered, tags):
        """Create a sample workspace XML file."""
        parent_suffix = f"_from-{parent}" if parent else ""
        filename = f"{seq}_{slug}_{status}{parent_suffix}.xml"

        delta_xml = "\n    ".join(f"<delta>{f}</delta>" for f in delta_files)
        pattern_xml = "\n    ".join(
            f'<pattern name="{t.replace("#pattern/", "")}"/>'
            for t in tags if t.startswith("#pattern/")
        )
        failure_xml = "\n    ".join(
            f'<failure name="{t.replace("#failure/", "")}"/>'
            for t in tags if t.startswith("#failure/")
        )
        constraint_xml = "\n    ".join(
            f'<constraint name="{t.replace("#constraint/", "")}"/>'
            for t in tags if t.startswith("#constraint/")
        )

        xml_content = f'''<?xml version="1.0" ?>
<workspace id="{seq}-{slug}" type="BUILD" mode="FULL" status="{status}">
  <implementation>
    {delta_xml}
    <verify>pytest -v</verify>
  </implementation>
  <prior_knowledge>
    {pattern_xml}
    {failure_xml}
  </prior_knowledge>
  <delivered status="{status}">{delivered}</delivered>
</workspace>'''

        (workspace_dir / filename).write_text(xml_content)

    def teardown(self):
        """Clean up temp directory."""
        if self.tmpdir:
            shutil.rmtree(self.tmpdir)


# --- mine_workspace tests ---

def test_mine_workspace_creates_index(fixture):
    """mine_workspace creates decision index from workspace files."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"

    result = fixture.memory.mine_workspace(workspace_dir, memory_path)

    assert "decisions" in result
    assert len(result["decisions"]) == 4
    assert "001" in result["decisions"]
    assert "002" in result["decisions"]
    assert "003" in result["decisions"]
    assert "004" in result["decisions"]
    print("  PASS: mine_workspace creates index")


def test_mine_workspace_captures_metadata(fixture):
    """mine_workspace captures slug, status, delta_files, delivered."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"

    result = fixture.memory.mine_workspace(workspace_dir, memory_path)

    d001 = result["decisions"]["001"]
    assert d001["slug"] == "setup-auth"
    assert d001["status"] == "complete"
    assert "src/auth.py" in d001["delta_files"]
    assert "Implemented auth module" in d001["delivered"]
    print("  PASS: mine_workspace captures metadata")


def test_mine_workspace_builds_lineage(fixture):
    """mine_workspace builds lineage edges from parent suffixes."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"

    result = fixture.memory.mine_workspace(workspace_dir, memory_path)

    lineage = result["edges"]["lineage"]
    assert lineage.get("002") == "001"
    assert lineage.get("003") == "002"
    assert lineage.get("004") == "002"
    assert "001" not in lineage  # Root has no parent
    print("  PASS: mine_workspace builds lineage")


def test_mine_workspace_builds_file_impact(fixture):
    """mine_workspace builds file_impact edges from delta files."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"

    result = fixture.memory.mine_workspace(workspace_dir, memory_path)

    file_impact = result["edges"]["file_impact"]
    assert "src/auth.py" in file_impact
    assert "001" in file_impact["src/auth.py"]
    assert "002" in file_impact["src/auth.py"]
    assert "src/routes.py" in file_impact
    assert "002" in file_impact["src/routes.py"]
    assert "003" in file_impact["src/routes.py"]
    print("  PASS: mine_workspace builds file_impact")


def test_mine_workspace_extracts_tags(fixture):
    """mine_workspace extracts pattern/failure tags from XML."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"

    result = fixture.memory.mine_workspace(workspace_dir, memory_path)

    d001 = result["decisions"]["001"]
    assert "#pattern/session-token" in d001["tags"]
    d004 = result["decisions"]["004"]
    assert "#failure/circular-import" in d004["tags"]
    print("  PASS: mine_workspace extracts tags")


# --- query_decisions tests ---

def test_query_decisions_all(fixture):
    """query_decisions without topic returns all decisions."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.query_decisions(None, memory)

    assert len(results) == 4
    print("  PASS: query_decisions returns all")


def test_query_decisions_by_slug(fixture):
    """query_decisions filters by slug (with semantic expansion)."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    # "auth" expands via concepts.py to include "login", so both match
    results = fixture.memory.query_decisions("auth", memory)
    slugs = [r["slug"] for r in results]
    assert "setup-auth" in slugs
    # "add-login" also matches due to semantic expansion (auth → login)
    assert "add-login" in slugs

    # Test exact slug match (no expansion)
    results = fixture.memory.query_decisions("logout", memory)
    assert len(results) == 1
    assert results[0]["slug"] == "add-logout"
    print("  PASS: query_decisions filters by slug")


def test_query_decisions_by_file(fixture):
    """query_decisions finds decisions by delta file."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.query_decisions("routes", memory)

    # Should match add-login and add-logout (both have routes.py)
    slugs = [r["slug"] for r in results]
    assert "add-login" in slugs
    assert "add-logout" in slugs
    print("  PASS: query_decisions filters by file")


def test_query_decisions_by_tag(fixture):
    """query_decisions finds decisions by tag."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.query_decisions("session-token", memory)

    slugs = [r["slug"] for r in results]
    assert "setup-auth" in slugs
    assert "add-login" in slugs
    print("  PASS: query_decisions filters by tag")


# --- get_decision tests ---

def test_get_decision_by_seq(fixture):
    """get_decision retrieves decision by sequence number."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    d = fixture.memory.get_decision("001", memory)

    assert d is not None
    assert d["seq"] == "001"
    assert d["slug"] == "setup-auth"
    print("  PASS: get_decision by seq")


def test_get_decision_normalizes_seq(fixture):
    """get_decision normalizes sequence number (1 → 001)."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    d = fixture.memory.get_decision("1", memory)

    assert d is not None
    assert d["seq"] == "001"
    print("  PASS: get_decision normalizes seq")


def test_get_decision_not_found(fixture):
    """get_decision returns None for missing seq."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    d = fixture.memory.get_decision("999", memory)

    assert d is None
    print("  PASS: get_decision not found")


# --- get_lineage tests ---

def test_get_lineage_chain(fixture):
    """get_lineage returns ancestry chain from root to target."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    chain = fixture.memory.get_lineage("003", memory)

    assert chain == ["001", "002", "003"]
    print("  PASS: get_lineage chain")


def test_get_lineage_root(fixture):
    """get_lineage for root returns single-element chain."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    chain = fixture.memory.get_lineage("001", memory)

    assert chain == ["001"]
    print("  PASS: get_lineage root")


def test_get_lineage_branch(fixture):
    """get_lineage handles branch (004 also descends from 002)."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    chain = fixture.memory.get_lineage("004", memory)

    assert chain == ["001", "002", "004"]
    print("  PASS: get_lineage branch")


# --- trace_tag tests ---

def test_trace_tag_finds_decisions(fixture):
    """trace_tag finds decisions using a specific tag."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.trace_tag("#pattern/session-token", memory)

    seqs = [r["seq"] for r in results]
    assert "001" in seqs
    assert "002" in seqs
    assert "003" not in seqs  # No tags
    print("  PASS: trace_tag finds decisions")


def test_trace_tag_empty(fixture):
    """trace_tag returns empty for unused tag."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.trace_tag("#pattern/nonexistent", memory)

    assert len(results) == 0
    print("  PASS: trace_tag empty")


# --- impact_file tests ---

def test_impact_file_finds_decisions(fixture):
    """impact_file finds decisions affecting a file."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.impact_file("auth.py", memory)

    seqs = [r["seq"] for r in results]
    assert "001" in seqs
    assert "002" in seqs
    assert "003" not in seqs
    print("  PASS: impact_file finds decisions")


def test_impact_file_partial_match(fixture):
    """impact_file matches partial file paths."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    results = fixture.memory.impact_file("routes", memory)

    seqs = [r["seq"] for r in results]
    assert "002" in seqs
    assert "003" in seqs
    print("  PASS: impact_file partial match")


# --- find_stale tests ---

def test_find_stale_empty_when_fresh(fixture):
    """find_stale returns empty when all decisions are recent."""
    workspace_dir = fixture.tmpdir / ".ftl" / "workspace"
    memory_path = fixture.tmpdir / ".ftl" / "memory.json"
    memory = fixture.memory.mine_workspace(workspace_dir, memory_path)

    # All files were just created, should be fresh
    results = fixture.memory.find_stale(1, memory)

    assert len(results) == 0
    print("  PASS: find_stale empty when fresh")


# --- add_signal tests ---

def test_add_signal_to_failure(fixture):
    """add_signal increments/decrements failure signal."""
    memory = fixture.memory._empty_memory()
    memory = fixture.memory.add_failure(memory, {
        "name": "test-failure",
        "trigger": "error",
        "fix": "fix it"
    })

    assert memory["failures"][0]["signal"] == 0

    memory = fixture.memory.add_signal(memory, "f001", "+")
    assert memory["failures"][0]["signal"] == 1

    memory = fixture.memory.add_signal(memory, "f001", "+")
    assert memory["failures"][0]["signal"] == 2

    memory = fixture.memory.add_signal(memory, "f001", "-")
    assert memory["failures"][0]["signal"] == 1
    print("  PASS: add_signal to failure")


def test_add_signal_to_discovery(fixture):
    """add_signal works on discoveries too."""
    memory = fixture.memory._empty_memory()
    memory = fixture.memory.add_discovery(memory, {
        "name": "test-discovery",
        "trigger": "when",
        "insight": "what"
    })

    assert memory["discoveries"][0]["signal"] == 0

    memory = fixture.memory.add_signal(memory, "d001", "-")
    assert memory["discoveries"][0]["signal"] == -1
    print("  PASS: add_signal to discovery")


def test_add_signal_nonexistent(fixture):
    """add_signal on nonexistent ID is a no-op."""
    memory = fixture.memory._empty_memory()

    # Should not raise
    memory = fixture.memory.add_signal(memory, "f999", "+")
    print("  PASS: add_signal nonexistent")


def main():
    lib_path = get_lib_path()
    if not lib_path or not Path(lib_path).exists():
        print("ERROR: FTL_LIB not set or doesn't exist")
        print("Set FTL_LIB environment variable or ensure ~/.config/ftl/paths.sh exists")
        return 1

    print(f"Testing memory decisions with FTL_LIB={lib_path}\n")

    memory = import_memory(lib_path)
    fixture = TestFixture(memory)

    tests = [
        # mine_workspace
        test_mine_workspace_creates_index,
        test_mine_workspace_captures_metadata,
        test_mine_workspace_builds_lineage,
        test_mine_workspace_builds_file_impact,
        test_mine_workspace_extracts_tags,
        # query_decisions
        test_query_decisions_all,
        test_query_decisions_by_slug,
        test_query_decisions_by_file,
        test_query_decisions_by_tag,
        # get_decision
        test_get_decision_by_seq,
        test_get_decision_normalizes_seq,
        test_get_decision_not_found,
        # get_lineage
        test_get_lineage_chain,
        test_get_lineage_root,
        test_get_lineage_branch,
        # trace_tag
        test_trace_tag_finds_decisions,
        test_trace_tag_empty,
        # impact_file
        test_impact_file_finds_decisions,
        test_impact_file_partial_match,
        # find_stale
        test_find_stale_empty_when_fresh,
        # add_signal
        test_add_signal_to_failure,
        test_add_signal_to_discovery,
        test_add_signal_nonexistent,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            fixture.setup()
            test(fixture)
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {test.__name__}: {e}")
            failed += 1
        finally:
            fixture.teardown()

    print(f"\n{passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
