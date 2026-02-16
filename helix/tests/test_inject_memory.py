"""Tests for SubagentStart memory injection hook."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

# Ensure lib is importable
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))


class TestParseParentTranscript:
    """Tests for parsing parent transcript (objective + injection state)."""

    def test_extracts_objective_from_task_tool_use(self, tmp_path):
        """Finds OBJECTIVE in Task tool_use prompt."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective == "Implement JWT authentication"
        assert has_insights is False

    def test_uses_last_task_tool_use(self, tmp_path):
        """When multiple Task tool_uses exist, uses the last one."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective == "Build the API layer"
        assert has_insights is False

    def test_skips_non_helix_agents(self, tmp_path):
        """Ignores Task tool_use for non-helix agents."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective is None
        assert has_insights is False

    def test_missing_file_returns_none(self):
        """Returns (None, False) for non-existent transcript."""
        from lib.hooks.inject_memory import _parse_parent_transcript
        objective, has_insights = _parse_parent_transcript("/nonexistent/path.jsonl")
        assert objective is None
        assert has_insights is False

    def test_no_objective_returns_none(self, tmp_path):
        """Returns None when no OBJECTIVE field — avoids noisy recall queries."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective is None
        assert has_insights is False

    def test_skips_non_tool_use_content(self, tmp_path):
        """Handles entries with string content (not tool_use blocks)."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective == "The actual objective"
        assert has_insights is False

    def test_empty_transcript_returns_none(self, tmp_path):
        """Returns (None, False) for empty transcript file."""
        from lib.hooks.inject_memory import _parse_parent_transcript

        transcript = tmp_path / "transcript.jsonl"
        transcript.write_text("")

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective is None
        assert has_insights is False

    def test_detects_insights_in_prompt(self, tmp_path):
        """Returns has_insights=True when INSIGHTS section exists."""
        from lib.hooks.inject_memory import _parse_parent_transcript

        transcript = tmp_path / "transcript.jsonl"
        entry = {
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "name": "Task",
                    "input": {
                        "subagent_type": "helix:helix-builder",
                        "prompt": "TASK: Build\nOBJECTIVE: Build it\nINSIGHTS (from past experience):\n  - [72%] Use JWT\nINJECTED: [\"insight-1\"]"
                    }
                }]
            }
        }
        transcript.write_text(json.dumps(entry) + "\n")

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert has_insights is True
        assert objective is not None

    def test_returns_false_without_insights(self, tmp_path):
        """Returns has_insights=False when no INSIGHTS section."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        _, has_insights = _parse_parent_transcript(str(transcript))
        assert has_insights is False

    def test_non_helix_agent_insights_ignored(self, tmp_path):
        """Returns (None, False) when last Task isn't a helix agent even with INSIGHTS."""
        from lib.hooks.inject_memory import _parse_parent_transcript

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

        objective, has_insights = _parse_parent_transcript(str(transcript))
        assert objective is None
        assert has_insights is False


class TestSideband:
    """Tests for sideband file write/read/cleanup."""

    def test_write_and_read_sideband(self, tmp_path, monkeypatch):
        """Write sideband, read back names + objective, verify cleanup."""
        from lib.hooks import inject_memory
        from lib.hooks import extract_learning

        # Point both modules' helix dir to tmp
        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        inject_memory._write_sideband("agent-123", ["insight-a", "insight-b"],
                                       objective="Implement JWT authentication")

        # Verify file exists
        sideband_file = tmp_path / "injected" / "agent-123.json"
        assert sideband_file.exists()

        # Verify content
        data = json.loads(sideband_file.read_text())
        assert set(data["names"]) == {"insight-a", "insight-b"}
        assert data["objective"] == "Implement JWT authentication"

        # Read and verify
        names, objective = extract_learning._read_sideband("agent-123")
        assert set(names) == {"insight-a", "insight-b"}
        assert objective == "Implement JWT authentication"

        # File should be cleaned up after read
        assert not sideband_file.exists()

    def test_read_missing_sideband_returns_empty(self, tmp_path, monkeypatch):
        """Returns empty tuple when sideband file doesn't exist."""
        from lib.hooks import extract_learning
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        names, objective = extract_learning._read_sideband("nonexistent-agent")
        assert names == []
        assert objective is None

    def test_write_creates_directory(self, tmp_path, monkeypatch):
        """_write_sideband creates injected/ directory if missing."""
        from lib.hooks import inject_memory
        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)

        inject_memory._write_sideband("agent-abc", ["name-1"], objective="Build feature")

        assert (tmp_path / "injected" / "agent-abc.json").exists()
        data = json.loads((tmp_path / "injected" / "agent-abc.json").read_text())
        assert data["objective"] == "Build feature"

    def test_read_handles_corrupt_json(self, tmp_path, monkeypatch):
        """Returns empty tuple for corrupt sideband file."""
        from lib.hooks import extract_learning
        monkeypatch.setattr(extract_learning, "get_helix_dir", lambda: tmp_path)

        injected_dir = tmp_path / "injected"
        injected_dir.mkdir()
        (injected_dir / "agent-bad.json").write_text("not json")

        names, objective = extract_learning._read_sideband("agent-bad")
        assert names == []
        assert objective is None


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

        mock_memories = [
            {"name": "planning-insight-1", "content": "Separate migration tasks", "_effectiveness": 0.65},
        ]

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Add user authentication", False))

        mock_memory_core = MagicMock()
        mock_memory_core.recall = lambda q, limit=5: mock_memories
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-planner",
            "agent_id": "planner-001",
            "transcript_path": "/fake/transcript"
        })

        assert "additionalContext" in result
        assert "INSIGHTS" in result["additionalContext"]
        assert "Separate migration tasks" in result["additionalContext"]

        # Sideband file should exist
        sideband = tmp_path / "injected" / "planner-001.json"
        assert sideband.exists()

    def test_builder_with_existing_insights_skips_entirely(self, tmp_path, monkeypatch):
        """Builder with orchestrator-injected insights: no sideband, no additionalContext.

        Orchestrator-injected builders have authoritative INJECTED in their transcript.
        Hook skips recall and sideband to avoid noise from imprecise objective extraction
        in parallel spawns.
        """
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Implement authentication", True))

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
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Optimize database queries", False))

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

    def test_empty_recall_returns_cold_start(self, tmp_path, monkeypatch):
        """Empty recall result with zero total insights produces NO_PRIOR_MEMORY signal."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Some objective", False))

        mock_memory_core = MagicMock()
        mock_memory_core.recall = lambda q, limit=5: []
        mock_memory_core.count = lambda: 0
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

    def test_empty_recall_with_existing_insights_returns_no_matching(self, tmp_path, monkeypatch):
        """Empty recall with total_insights > 0 produces NO_MATCHING_INSIGHTS signal."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Niche objective", False))

        mock_memory_core = MagicMock()
        mock_memory_core.recall = lambda q, limit=5: []
        mock_memory_core.count = lambda: 12
        monkeypatch.setitem(sys.modules, "memory.core", mock_memory_core)

        result = inject_memory.process_hook_input({
            "agent_type": "helix:helix-planner",
            "agent_id": "planner-003",
            "transcript_path": "/fake/transcript"
        })

        assert "additionalContext" in result
        assert "NO_MATCHING_INSIGHTS" in result["additionalContext"]
        assert "NO_PRIOR_MEMORY" not in result["additionalContext"]

    def test_recall_error_returns_empty_gracefully(self, tmp_path, monkeypatch):
        """Recall failure degrades gracefully to cold start."""
        from lib.hooks import inject_memory

        monkeypatch.setattr(inject_memory, "get_helix_dir", lambda: tmp_path)
        monkeypatch.setattr(inject_memory, "_parse_parent_transcript", lambda tp: ("Some objective", False))

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
