"""Tests for SubagentStart memory injection hook."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))


class TestExtractObjective:
    """Tests for extracting objective from parent transcript."""

    def test_extracts_objective_from_task_tool_use(self, tmp_path):
        """Finds OBJECTIVE in Task tool_use prompt."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-builder",
                        "prompt": "TASK_ID: t1\nTASK: Build auth\nOBJECTIVE: Implement JWT authentication\nVERIFY: Run tests"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        result = _extract_objective(str(transcript))
        assert result == "Implement JWT authentication"

    def test_uses_last_task_tool_use(self, tmp_path):
        """When multiple Task tool_uses exist, uses the last one."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        entries = [
            {"message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Task", "input": {
                    "subagent_type": "helix:helix-explorer",
                    "prompt": "SCOPE: src/\nOBJECTIVE: Explore the codebase"
                }}
            ]}},
            {"message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Task", "input": {
                    "subagent_type": "helix:helix-builder",
                    "prompt": "TASK_ID: t2\nOBJECTIVE: Build the API layer\nVERIFY: tests pass"
                }}
            ]}},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result = _extract_objective(str(transcript))
        assert result == "Build the API layer"

    def test_skips_non_helix_agents(self, tmp_path):
        """Ignores Task tool_use for non-helix agents."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "other-agent",
                        "prompt": "OBJECTIVE: Not helix"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        result = _extract_objective(str(transcript))
        assert result is None

    def test_missing_file_returns_none(self):
        """Returns None for non-existent transcript."""
        from lib.hooks.inject_memory import _extract_objective
        result = _extract_objective("/nonexistent/path.jsonl")
        assert result is None

    def test_fallback_to_prompt_substring(self, tmp_path):
        """Falls back to first 500 chars when no OBJECTIVE field."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-planner",
                        "prompt": "Some planner prompt without standard fields"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        result = _extract_objective(str(transcript))
        assert result == "Some planner prompt without standard fields"

    def test_skips_non_tool_use_content(self, tmp_path):
        """Handles entries with string content (not tool_use blocks)."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        entries = [
            {"message": {"role": "user", "content": "Do something"}},
            {"message": {"role": "assistant", "content": "Thinking..."}},
            {"message": {"role": "assistant", "content": [
                {"type": "tool_use", "name": "Task", "input": {
                    "subagent_type": "helix:helix-builder",
                    "prompt": "OBJECTIVE: The actual objective\nVERIFY: check"
                }}
            ]}},
        ]
        transcript.write_text("\n".join(json.dumps(e) for e in entries) + "\n")

        result = _extract_objective(str(transcript))
        assert result == "The actual objective"

    def test_empty_transcript_returns_none(self, tmp_path):
        """Returns None for empty transcript file."""
        from lib.hooks.inject_memory import _extract_objective

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("")

        result = _extract_objective(str(transcript))
        assert result is None


class TestPromptHasInsights:
    """Tests for detecting existing INSIGHTS in spawn prompt."""

    def test_detects_insights_in_prompt(self, tmp_path):
        """Returns True when INSIGHTS section exists."""
        from lib.hooks.inject_memory import _prompt_has_insights

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-builder",
                        "prompt": "TASK: Build\nINSIGHTS (from past experience):\n  - [72%] Use JWT\nINJECTED: [\"insight-1\"]"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        assert _prompt_has_insights(str(transcript)) is True

    def test_returns_false_without_insights(self, tmp_path):
        """Returns False when no INSIGHTS section."""
        from lib.hooks.inject_memory import _prompt_has_insights

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-builder",
                        "prompt": "TASK: Build something\nOBJECTIVE: Just build it"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        assert _prompt_has_insights(str(transcript)) is False

    def test_returns_false_for_missing_file(self):
        """Returns False when transcript doesn't exist."""
        from lib.hooks.inject_memory import _prompt_has_insights
        assert _prompt_has_insights("/nonexistent/path") is False

    def test_returns_false_for_non_helix_agent(self, tmp_path):
        """Returns False when last Task isn't a helix agent."""
        from lib.hooks.inject_memory import _prompt_has_insights

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "other-agent",
                        "prompt": "INSIGHTS (from past experience):\n  - [72%] Some insight"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        assert _prompt_has_insights(str(transcript)) is False


class TestSideband:
    """Tests for sideband file write/read/cleanup."""

    def test_write_and_read_sideband(self, tmp_path, monkeypatch):
        """Write sideband, read back names, verify cleanup."""
        from lib.hooks import inject_memory
        from lib.hooks import extract_learning

        # Point both modules' helix dir to tmp
        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        inject_memory._write_sideband("agent-123", ["insight-a", "insight-b"])

        # Verify file exists
        sideband_file = tmp_path / "injected" / "agent-123.json"
        assert sideband_file.exists()

        # Verify content
        data = json.loads(sideband_file.read_text())
        assert set(data["names"]) == {"insight-a", "insight-b"}
        assert "ts" in data

        # Read and verify
        names = extract_learning._read_sideband("agent-123")
        assert set(names) == {"insight-a", "insight-b"}

        # File should be cleaned up after read
        assert not sideband_file.exists()

    def test_read_missing_sideband_returns_empty(self, tmp_path, monkeypatch):
        """Returns empty list when sideband file doesn't exist."""
        from lib.hooks import extract_learning
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        names = extract_learning._read_sideband("nonexistent-agent")
        assert names == []

    def test_write_creates_directory(self, tmp_path, monkeypatch):
        """_write_sideband creates injected/ directory if missing."""
        from lib.hooks import inject_memory
        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)

        inject_memory._write_sideband("agent-abc", ["name-1"])

        assert (tmp_path / "injected" / "agent-abc.json").exists()

    def test_read_handles_corrupt_json(self, tmp_path, monkeypatch):
        """Returns empty list for corrupt sideband file."""
        from lib.hooks import extract_learning
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        injected_dir = tmp_path / "injected"
        injected_dir.mkdir()
        (injected_dir / "agent-bad.json").write_text("not json")

        names = extract_learning._read_sideband("agent-bad")
        assert names == []


class TestFormatAdditionalContext:
    """Tests for formatting insights as additionalContext."""

    def test_formats_insights(self):
        """Formats memories into additionalContext with INSIGHTS and INJECTED."""
        from lib.hooks.inject_memory import _format_additional_context

        memories = [
            {"name": "insight-1", "content": "When X, do Y", "_effectiveness": 0.72},
            {"name": "insight-2", "content": "When A, do B", "_effectiveness": 0.45},
        ]
        result = _format_additional_context(memories)

        assert "additionalContext" in result
        ctx = result["additionalContext"]
        assert "INSIGHTS (from past experience):" in ctx
        assert "[72%] When X, do Y" in ctx
        assert "[45%] When A, do B" in ctx
        assert 'INJECTED: ["insight-1", "insight-2"]' in ctx

    def test_empty_memories_returns_cold_start(self):
        """Empty memories produce NO_PRIOR_MEMORY signal."""
        from lib.hooks.inject_memory import _format_additional_context

        result = _format_additional_context([])
        assert "NO_PRIOR_MEMORY" in result["additionalContext"]


class TestLogging:
    """Tests for injection logging."""

    def test_logs_successful_injection(self, tmp_path, monkeypatch):
        """Successful injection writes INJECT line to extraction.log."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)

        inject_memory._log_injection(
            "builder-123", "helix:helix-builder", 3, True, True
        )

        log_file = tmp_path / "extraction.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "INJECT" in content
        assert "builder-123" in content
        assert "insights=3" in content
        assert "sideband+context" in content

    def test_logs_skip_when_already_injected(self, tmp_path, monkeypatch):
        """Orchestrator-injected builders log 'skip'."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)

        inject_memory._log_injection(
            "builder-456", "helix:helix-builder", 0, False, False
        )

        content = (tmp_path / "extraction.log").read_text()
        assert "skip" in content


class TestProcessHookInput:
    """Tests for the main hook processing function."""

    def test_skips_non_helix_agent(self):
        """Non-helix agents get empty response."""
        from lib.hooks.inject_memory import process_hook_input

        result = process_hook_input({"agent_type": "some-other-agent", "agent_id": "test"})
        assert result == {}

    def test_skips_missing_agent_id(self):
        """Missing agent_id gets empty response."""
        from lib.hooks.inject_memory import process_hook_input

        result = process_hook_input({"agent_type": "helix:helix-builder", "agent_id": ""})
        assert result == {}

    def test_no_objective_returns_cold_start(self):
        """No extractable objective returns cold start signal."""
        from lib.hooks.inject_memory import process_hook_input

        result = process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": "builder-002",
            "transcript_path": "/nonexistent/path"
        })

        assert "additionalContext" in result
        assert "NO_PRIOR_MEMORY" in result["additionalContext"]

    def test_planner_gets_injection(self, tmp_path, monkeypatch):
        """Planner without existing insights gets additionalContext."""
        from lib.hooks import inject_memory

        # Create parent transcript with planner spawn
        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-planner",
                        "prompt": "OBJECTIVE: Add user authentication to the API"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        # Mock recall to return some insights
        mock_memories = [
            {"name": "planning-insight-1", "content": "Separate migration tasks", "_effectiveness": 0.65},
        ]

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)

        with patch.dict("sys.modules", {}):
            with patch("lib.hooks.inject_memory.process_hook_input") as _:
                pass  # clear any cached imports

        # Directly test with mocked recall
        original_process = inject_memory.process_hook_input

        def mock_recall(query, limit=5):
            return mock_memories

        with patch.object(sys.modules.get("memory.core", MagicMock()), "recall", mock_recall, create=True):
            # Patch at the import point
            import importlib
            with patch("builtins.__import__", wraps=__builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__) as mock_import:
                # Simpler approach: just mock at module level
                pass

        # Use a cleaner approach - patch the recall call inside process_hook_input
        monkeypatch.setattr(inject_memory, "_extract_objective", lambda tp: "Add user authentication")
        monkeypatch.setattr(inject_memory, "_prompt_has_insights", lambda tp: False)

        # Mock the recall import inside the function
        mock_memory_core = MagicMock()
        mock_memory_core.recall = mock_recall
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-planner",
            "agent_id": "planner-001",
            "transcript_path": str(transcript)
        })

        # Should have additionalContext with insights
        assert "additionalContext" in result
        assert "INSIGHTS" in result["additionalContext"]
        assert "Separate migration tasks" in result["additionalContext"]

        # Sideband file should exist
        sideband = tmp_path / "injected" / "planner-001.json"
        assert sideband.exists()

        # Clean up sys.modules
        if "memory.core" in sys.modules:
            del sys.modules["memory.core"]

    def test_builder_with_existing_insights_skips_entirely(self, tmp_path, monkeypatch):
        """Builder with orchestrator-injected insights: no sideband, no additionalContext.

        Orchestrator-injected builders have authoritative INJECTED in their transcript.
        Hook skips recall and sideband to avoid noise from imprecise objective extraction
        in parallel spawns.
        """
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_extract_objective", lambda tp: "Implement authentication")
        monkeypatch.setattr(inject_memory, "_prompt_has_insights", lambda tp: True)

        # recall should NOT be called — no mock needed
        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": "builder-001",
            "transcript_path": "/fake/transcript"
        })

        # No additionalContext, no sideband
        assert result == {}
        assert not (tmp_path / "injected" / "builder-001.json").exists()

    def test_builder_without_insights_gets_context(self, tmp_path, monkeypatch):
        """Builder without orchestrator injection gets full additionalContext."""
        from lib.hooks import inject_memory

        mock_memories = [
            {"name": "perf-insight", "content": "Use indexes for queries", "_effectiveness": 0.55},
        ]

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_extract_objective", lambda tp: "Optimize database queries")
        monkeypatch.setattr(inject_memory, "_prompt_has_insights", lambda tp: False)

        mock_memory_core = MagicMock()
        mock_memory_core.recall = lambda q, limit=5: mock_memories
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": "builder-003",
            "transcript_path": "/fake/transcript"
        })

        # Should have additionalContext
        assert "additionalContext" in result
        assert "Use indexes for queries" in result["additionalContext"]
        assert "INJECTED" in result["additionalContext"]

        # Clean up
        if "memory.core" in sys.modules:
            del sys.modules["memory.core"]

    def test_empty_recall_returns_cold_start(self, tmp_path, monkeypatch):
        """Empty recall result produces NO_PRIOR_MEMORY signal."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_extract_objective", lambda tp: "Some objective")
        monkeypatch.setattr(inject_memory, "_prompt_has_insights", lambda tp: False)

        mock_memory_core = MagicMock()
        mock_memory_core.recall = lambda q, limit=5: []
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-planner",
            "agent_id": "planner-002",
            "transcript_path": "/fake/transcript"
        })

        assert "additionalContext" in result
        assert "NO_PRIOR_MEMORY" in result["additionalContext"]

        # No sideband file (no names to write)
        assert not (tmp_path / "injected" / "planner-002.json").exists()

        # Clean up
        if "memory.core" in sys.modules:
            del sys.modules["memory.core"]

    def test_recall_error_returns_empty_gracefully(self, tmp_path, monkeypatch):
        """Recall failure degrades gracefully to cold start."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_extract_objective", lambda tp: "Some objective")
        monkeypatch.setattr(inject_memory, "_prompt_has_insights", lambda tp: False)

        mock_memory_core = MagicMock()
        mock_memory_core.recall = MagicMock(side_effect=Exception("DB error"))
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-builder",
            "agent_id": "builder-err",
            "transcript_path": "/fake/transcript"
        })

        # Should degrade to cold start, not crash
        assert "additionalContext" in result
        assert "NO_PRIOR_MEMORY" in result["additionalContext"]

        # Clean up
        if "memory.core" in sys.modules:
            del sys.modules["memory.core"]
