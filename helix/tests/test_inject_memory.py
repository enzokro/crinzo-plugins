#!/usr/bin/env python3
"""Tests for inject_memory hook module."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))

from hooks.inject_memory import (
    process_hook_input,
    inject_for_explorer,
    inject_for_planner,
    inject_for_builder,
    format_explorer_context,
    format_planner_context,
)


class TestProcessHookInput:
    """Tests for process_hook_input function."""

    def test_non_task_tool(self):
        """Non-Task tools should pass through."""
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        result = process_hook_input(hook_input)
        assert result == {}

    def test_non_helix_agent(self):
        """Non-helix agents should pass through."""
        hook_input = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "general-purpose",
                "prompt": "Do something",
            },
        }
        result = process_hook_input(hook_input)
        assert result == {}

    def test_no_inject_flag(self):
        """NO_INJECT: true should skip injection."""
        hook_input = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "helix:helix-explorer",
                "prompt": "SCOPE: src/\nNO_INJECT: true",
            },
        }
        result = process_hook_input(hook_input)
        assert result == {}

    def test_explorer_passes_through(self):
        """Explorer prompts should pass through unmodified - explorer runs own recall()."""
        hook_input = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "helix:helix-explorer",
                "prompt": "SCOPE: src/\nOBJECTIVE: Find auth",
            },
            "tool_use_id": "test-123",
        }

        result = process_hook_input(hook_input)

        # Explorer injection removed - agent runs its own recall()
        assert result == {}

    @patch("hooks.inject_memory.build_planner_context")
    @patch("hooks.inject_memory.store_injection_state")
    def test_planner_injection(self, mock_store, mock_build):
        """Planner prompts should get project context."""
        mock_build.return_value = {
            "decisions": ["Decision 1"],
            "conventions": [],
            "recent_evolution": [],
            "injected": ["decision-1"],
        }

        hook_input = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "helix:helix-planner",
                "prompt": "OBJECTIVE: Add auth\nEXPLORATION: {}",
            },
            "tool_use_id": "test-456",
        }

        result = process_hook_input(hook_input)

        assert "updatedInput" in result
        assert "# PROJECT CONTEXT" in result["updatedInput"]["prompt"]

    @patch("hooks.inject_memory.build_context")
    @patch("hooks.inject_memory.store_injection_state")
    def test_builder_injection(self, mock_store, mock_build):
        """Builder prompts should get full context."""
        mock_build.return_value = {
            "prompt": "TASK_ID: 3\nTASK: test\nFAILURES_TO_AVOID: []",
            "injected": ["pattern-1"],
        }

        hook_input = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "helix:helix-builder",
                "prompt": "TASK_ID: 3\nTASK: test\nOBJECTIVE: Do thing",
            },
            "tool_use_id": "test-789",
        }

        result = process_hook_input(hook_input)

        assert "updatedInput" in result
        # Builder gets fully replaced prompt
        assert "TASK_ID:" in result["updatedInput"]["prompt"]


class TestFormatContext:
    """Tests for context formatting functions."""

    def test_explorer_context_with_facts(self):
        ctx = {
            "known_facts": ["Fact 1", "Fact 2"],
            "relevant_failures": ["Fail 1 -> Fix 1"],
        }
        result = format_explorer_context(ctx)
        assert "# MEMORY CONTEXT" in result
        assert "Known Facts" in result
        assert "- Fact 1" in result
        assert "Relevant Failures" in result
        assert "- Fail 1 -> Fix 1" in result

    def test_explorer_context_empty(self):
        ctx = {"known_facts": [], "relevant_failures": []}
        result = format_explorer_context(ctx)
        assert "No relevant memories found" in result

    def test_planner_context_with_decisions(self):
        ctx = {
            "decisions": ["Use OAuth"],
            "conventions": ["[80%] Use TypeScript"],
            "recent_evolution": [],
        }
        result = format_planner_context(ctx)
        assert "# PROJECT CONTEXT" in result
        assert "Prior Decisions" in result
        assert "- Use OAuth" in result
        assert "Conventions" in result

    def test_planner_context_empty(self):
        ctx = {"decisions": [], "conventions": [], "recent_evolution": []}
        result = format_planner_context(ctx)
        assert "No relevant project context found" in result


class TestInjectionState:
    """Tests for injection state storage."""

    @patch("hooks.inject_memory.get_injection_state_dir")
    @patch("hooks.inject_memory.build_planner_context")
    def test_injection_state_stored(self, mock_build, mock_dir):
        """Injection state should be written to file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_dir.return_value = Path(tmpdir)
            mock_build.return_value = {
                "decisions": [],
                "conventions": [],
                "recent_evolution": [],
                "injected": ["mem-1", "mem-2"],
            }

            hook_input = {
                "tool_name": "Task",
                "tool_input": {
                    "subagent_type": "helix:helix-planner",
                    "prompt": "OBJECTIVE: Test\nEXPLORATION: {}",
                },
                "tool_use_id": "test-state-123",
            }

            process_hook_input(hook_input)

            # Check state file was created
            state_file = Path(tmpdir) / "test-state-123.json"
            assert state_file.exists()

            state = json.loads(state_file.read_text())
            assert state["agent_type"] == "helix:helix-planner"
            assert state["injected_memories"] == ["mem-1", "mem-2"]


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
