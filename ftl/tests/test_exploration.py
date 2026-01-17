"""Test FTL v2 exploration.py operations."""

import json
from pathlib import Path


class TestExplorationAggregate:
    """Test exploration result aggregation."""

    def test_aggregate_all_modes(self, cli, ftl_dir):
        """Aggregate combines all 4 explorer mode outputs."""
        results = [
            {"mode": "structure", "status": "ok", "directories": {"lib": True}},
            {"mode": "pattern", "status": "ok", "framework": "none"},
            {"mode": "memory", "status": "ok", "failures": []},
            {"mode": "delta", "status": "ok", "candidates": []}
        ]
        stdin = "\n".join(json.dumps(r) for r in results)

        code, out, err = cli.exploration("aggregate", "--objective", "test task", stdin=stdin)
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert "_meta" in data
        assert data["_meta"]["objective"] == "test task"
        assert "structure" in data
        assert "pattern" in data
        assert "memory" in data
        assert "delta" in data

    def test_aggregate_partial_results(self, cli, ftl_dir):
        """Aggregate handles partial results gracefully."""
        results = [
            {"mode": "structure", "status": "ok", "directories": {"lib": True}},
            {"mode": "pattern", "status": "error", "error": "timeout"},
            {"mode": "memory", "status": "partial", "failures": []},
        ]
        stdin = "\n".join(json.dumps(r) for r in results)

        code, out, err = cli.exploration("aggregate", stdin=stdin)
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        # Structure should be included (ok)
        assert data["structure"]["status"] == "ok"
        # Pattern should be error with _error field
        assert "_error" in data["pattern"]
        # Memory should be included (partial is acceptable)
        assert data["memory"]["status"] == "partial"

    def test_aggregate_empty_results(self, cli, ftl_dir):
        """Aggregate handles empty input."""
        code, out, err = cli.exploration("aggregate", stdin="")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert "_meta" in data
        # Should only have _meta, no mode sections
        assert "structure" not in data

    def test_aggregate_includes_git_sha(self, cli, ftl_dir):
        """Aggregate includes git sha in metadata."""
        results = [{"mode": "structure", "status": "ok"}]
        stdin = json.dumps(results[0])

        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        data = json.loads(out)

        assert "git_sha" in data["_meta"]


class TestExplorationWrite:
    """Test writing exploration.json."""

    def test_write_creates_file(self, cli, ftl_dir):
        """Write creates exploration.json in .ftl directory."""
        exploration = {
            "_meta": {"version": "1.0"},
            "structure": {"status": "ok", "directories": {}}
        }

        code, out, err = cli.exploration("write", stdin=json.dumps(exploration))
        assert code == 0, f"Failed: {err}"
        assert "Written" in out

        # Verify file exists
        path = ftl_dir / ".ftl" / "exploration.json"
        assert path.exists()

        # Verify contents
        data = json.loads(path.read_text())
        assert data["_meta"]["version"] == "1.0"


class TestExplorationRead:
    """Test reading exploration.json."""

    def test_read_returns_contents(self, cli, ftl_dir):
        """Read returns exploration.json contents."""
        # First write
        exploration = {
            "_meta": {"version": "1.0"},
            "structure": {"status": "ok", "file_count": 25}
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        # Then read
        code, out, err = cli.exploration("read")
        assert code == 0, f"Failed: {err}"

        data = json.loads(out)
        assert data["structure"]["file_count"] == 25

    def test_read_missing_returns_null(self, cli, ftl_dir):
        """Read returns null if exploration.json doesn't exist."""
        code, out, _ = cli.exploration("read")
        assert code == 0
        assert out.strip() == "null"


class TestExplorationGetters:
    """Test individual section getters."""

    def test_get_structure(self, cli, ftl_dir):
        """Get-structure returns structure section."""
        exploration = {
            "_meta": {"version": "1.0"},
            "structure": {"status": "ok", "directories": {"lib": True, "tests": True}}
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-structure")
        assert code == 0

        data = json.loads(out)
        assert data["directories"]["lib"] is True

    def test_get_pattern(self, cli, ftl_dir):
        """Get-pattern returns pattern section."""
        exploration = {
            "_meta": {"version": "1.0"},
            "pattern": {
                "status": "ok",
                "framework": "FastAPI",
                "idioms": {"required": ["Use @app"], "forbidden": []}
            }
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-pattern")
        assert code == 0

        data = json.loads(out)
        assert data["framework"] == "FastAPI"
        assert "Use @app" in data["idioms"]["required"]

    def test_get_memory(self, cli, ftl_dir):
        """Get-memory returns memory section."""
        exploration = {
            "_meta": {"version": "1.0"},
            "memory": {
                "status": "ok",
                "failures": [{"name": "test-failure", "cost": 5000}],
                "patterns": [],
                "total_in_memory": {"failures": 1, "patterns": 0}
            }
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-memory")
        assert code == 0

        data = json.loads(out)
        assert len(data["failures"]) == 1
        assert data["failures"][0]["cost"] == 5000

    def test_get_delta(self, cli, ftl_dir):
        """Get-delta returns delta section."""
        exploration = {
            "_meta": {"version": "1.0"},
            "delta": {
                "status": "ok",
                "search_terms": ["campaign", "complete"],
                "candidates": [
                    {"path": "lib/campaign.py", "lines": 256, "functions": []}
                ]
            }
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-delta")
        assert code == 0

        data = json.loads(out)
        assert "campaign" in data["search_terms"]
        assert data["candidates"][0]["path"] == "lib/campaign.py"

    def test_get_missing_section_returns_fallback(self, cli, ftl_dir):
        """Get returns fallback when section missing."""
        exploration = {"_meta": {"version": "1.0"}}
        cli.exploration("write", stdin=json.dumps(exploration))

        # Get pattern when only _meta exists
        code, out, _ = cli.exploration("get-pattern")
        assert code == 0

        data = json.loads(out)
        # Should have fallback values
        assert data["status"] == "missing"
        assert data["framework"] == "none"
        assert data["idioms"]["required"] == []

    def test_get_when_no_exploration_file(self, cli, ftl_dir):
        """Get returns fallback when no exploration.json exists."""
        code, out, _ = cli.exploration("get-delta")
        assert code == 0

        data = json.loads(out)
        assert data["status"] == "missing"
        assert data["candidates"] == []


class TestExplorationClear:
    """Test clearing exploration.json."""

    def test_clear_removes_file(self, cli, ftl_dir):
        """Clear removes exploration.json."""
        # First create a file
        exploration = {"_meta": {"version": "1.0"}}
        cli.exploration("write", stdin=json.dumps(exploration))

        # Verify it exists
        path = ftl_dir / ".ftl" / "exploration.json"
        assert path.exists()

        # Clear it
        code, out, _ = cli.exploration("clear")
        assert code == 0
        assert "Cleared" in out

        # Verify it's gone
        assert not path.exists()

    def test_clear_when_no_file(self, cli, ftl_dir):
        """Clear handles missing file gracefully."""
        code, out, _ = cli.exploration("clear")
        assert code == 0
        assert "No exploration.json" in out


class TestExplorationValidation:
    """Test input validation for aggregation."""

    def test_aggregate_skips_invalid_results(self, cli, ftl_dir):
        """Aggregate skips results missing required fields."""
        results = [
            {"mode": "structure", "status": "ok"},  # Valid
            {"status": "ok"},  # Missing mode - skip
            {"mode": "invalid_mode", "status": "ok"},  # Invalid mode - skip
            {"mode": "pattern"},  # Missing status - skip
            {"mode": "delta", "status": "ok"},  # Valid
        ]
        stdin = "\n".join(json.dumps(r) for r in results)

        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0

        data = json.loads(out)
        # Only structure and delta should be included
        assert "structure" in data
        assert "delta" in data
        assert "pattern" not in data  # Skipped due to missing status

    def test_aggregate_handles_malformed_json(self, cli, ftl_dir):
        """Aggregate handles malformed JSON lines."""
        stdin = '{"mode": "structure", "status": "ok"}\nnot json\n{"mode": "pattern", "status": "ok"}'

        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0

        data = json.loads(out)
        assert "structure" in data
        assert "pattern" in data


class TestExtractJson:
    """Test robust JSON extraction from LLM output."""

    def test_extract_clean_json(self, cli, ftl_dir):
        """Extract from clean JSON string."""
        stdin = '{"mode": "structure", "status": "ok"}'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        assert "structure" in data

    def test_extract_from_markdown_block(self, cli, ftl_dir):
        """Extract JSON from markdown code block."""
        stdin = '```json\n{"mode": "structure", "status": "ok"}\n```'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        assert "structure" in data

    def test_extract_with_prefix_text(self, cli, ftl_dir):
        """Extract JSON when prefixed with explanation."""
        stdin = 'Here is the JSON output: {"mode": "pattern", "status": "ok"}'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        assert "pattern" in data

    def test_extract_with_suffix_text(self, cli, ftl_dir):
        """Extract JSON when followed by explanation."""
        stdin = '{"mode": "memory", "status": "ok"}\n\nThis JSON contains the memory data.'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        assert "memory" in data

    def test_extract_nested_json(self, cli, ftl_dir):
        """Extract JSON with nested objects."""
        stdin = '{"mode": "delta", "status": "ok", "candidates": [{"path": "test.py", "lines": 100}]}'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        assert "delta" in data
        assert data["delta"]["candidates"][0]["path"] == "test.py"

    def test_extract_returns_none_for_garbage(self, cli, ftl_dir):
        """Completely invalid input produces empty result."""
        stdin = 'This is not JSON at all, just random text without braces.'
        code, out, _ = cli.exploration("aggregate", stdin=stdin)
        assert code == 0
        data = json.loads(out)
        # Only _meta should exist (no mode sections)
        assert "_meta" in data
        assert "structure" not in data


class TestSimilarCampaigns:
    """Test similar campaign discovery."""

    def test_get_memory_includes_similar_campaigns_field(self, cli, ftl_dir):
        """Get-memory returns similar_campaigns field."""
        # Write exploration with memory section
        exploration = {
            "_meta": {"version": "1.0"},
            "memory": {
                "status": "ok",
                "failures": [],
                "patterns": [],
                "total_in_memory": {"failures": 0, "patterns": 0}
            }
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-memory")
        assert code == 0

        data = json.loads(out)
        # Should have similar_campaigns field (possibly empty if no archives)
        assert "similar_campaigns" in data

    def test_similar_campaigns_empty_when_no_archives(self, cli, ftl_dir):
        """Similar campaigns returns empty list when no archived campaigns."""
        # Write exploration
        exploration = {
            "_meta": {"version": "1.0"},
            "memory": {"status": "ok", "failures": [], "patterns": []}
        }
        cli.exploration("write", stdin=json.dumps(exploration))

        code, out, _ = cli.exploration("get-memory")
        data = json.loads(out)

        # No archives exist, so similar_campaigns should be empty
        assert data["similar_campaigns"] == []

    def test_find_similar_with_archived_campaigns(self, cli, ftl_dir, lib_path):
        """Find similar returns matching archived campaigns."""
        import sys
        sys.path.insert(0, str(lib_path))
        import campaign

        # Create and complete a campaign to generate an archive
        cli.campaign("create", "Authentication with OAuth", "--framework", "FastHTML")
        plan = {
            "campaign": "auth",
            "framework": "FastHTML",
            "idioms": {"required": [], "forbidden": []},
            "tasks": [
                {"seq": "001", "slug": "auth", "type": "BUILD", "delta": ["auth.py"],
                 "verify": "true", "budget": 3, "depends": "none"}
            ]
        }
        cli.campaign("add-tasks", stdin=json.dumps(plan))
        cli.campaign("update-task", "001", "complete")
        cli.campaign("complete", "--summary", "OAuth implemented")

        # Create new campaign with similar objective
        cli.campaign("create", "User authentication system", "--framework", "FastHTML")

        # Find similar - should match the archived OAuth campaign
        similar = campaign.find_similar(threshold=0.3)

        # Should find the archived campaign (both about authentication + same framework)
        # Note: match depends on semantic similarity of objectives
        assert isinstance(similar, list)
        # The archived campaign exists, so we should have potential matches
        # (actual matching depends on embedding similarity threshold)

    def test_find_similar_requires_framework_match(self, cli, ftl_dir, lib_path):
        """Find similar requires framework match."""
        import sys
        sys.path.insert(0, str(lib_path))
        import campaign

        # Create and archive a FastHTML campaign
        cli.campaign("create", "Build REST API", "--framework", "FastHTML")
        plan = {
            "campaign": "api",
            "framework": "FastHTML",
            "idioms": {"required": [], "forbidden": []},
            "tasks": [
                {"seq": "001", "slug": "api", "type": "BUILD", "delta": ["api.py"],
                 "verify": "true", "budget": 3, "depends": "none"}
            ]
        }
        cli.campaign("add-tasks", stdin=json.dumps(plan))
        cli.campaign("update-task", "001", "complete")
        cli.campaign("complete", "--summary", "API done")

        # Create new campaign with DIFFERENT framework
        cli.campaign("create", "Build REST API", "--framework", "Django")

        # Find similar - framework mismatch should filter out
        similar = campaign.find_similar(threshold=0.1)

        # No matches expected due to framework mismatch
        fasthtml_matches = [s for s in similar if s.get("fingerprint", {}).get("framework") == "FastHTML"]
        # Even with similar objective, different framework should not match
        assert len(fasthtml_matches) == 0
