#!/usr/bin/env python3
"""Memory injection hook for helix agents.

Called by PreToolUse hook on Task tool. Builds insight context
and enriches builder prompts with relevant memories.

NOTE: This module is now simplified - the orchestrator (SKILL.md) handles
most injection directly. This hook is a fallback for direct builder spawning.

Usage (from pretool-task.sh):
    python3 "$HELIX/lib/hooks/inject_memory.py" < hook_input.json
"""

import json
import sys
import uuid
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from injection import inject_context, format_prompt


def process_hook_input(hook_input: dict) -> dict:
    """Process PreToolUse hook input and return response.

    Args:
        hook_input: JSON from PreToolUse hook with:
            - tool_name: should be "Task"
            - tool_input: {subagent_type, prompt, ...}
            - tool_use_id: unique identifier

    Returns:
        Hook response dict:
            - {} if no modification
            - {"updatedInput": {...}} to modify
    """
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Task":
        return {}

    tool_input = hook_input.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    prompt = tool_input.get("prompt", "")

    # Only process helix builders (explorers/planners don't need injection)
    if subagent_type != "helix:helix-builder":
        return {}

    # Check for NO_INJECT flag
    if "NO_INJECT" in prompt:
        return {}

    # Check if already injected (has INJECTED: line)
    if "INJECTED:" in prompt:
        return {}

    # Extract objective from prompt for context lookup
    import re
    objective_match = re.search(r'OBJECTIVE:\s*(.+?)(?:\n|$)', prompt)
    objective = objective_match.group(1).strip() if objective_match else prompt[:200]

    # Get relevant insights
    context = inject_context(objective, limit=5)

    if not context["insights"]:
        return {}

    # Inject insights into prompt
    insight_block = "\nINSIGHTS (from past experience):\n"
    for insight in context["insights"]:
        insight_block += f"  - {insight}\n"
    insight_block += f"\nINJECTED: {json.dumps(context['names'])}\n"

    # Append to prompt
    updated_prompt = prompt + insight_block

    updated_input = dict(tool_input)
    updated_input["prompt"] = updated_prompt

    return {"updatedInput": updated_input}


def main():
    """Main entry point - read from stdin, write to stdout."""
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print("{}")
            return

        hook_input = json.loads(input_data)
        result = process_hook_input(hook_input)
        print(json.dumps(result))

    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        print("{}")

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        print("{}")


if __name__ == "__main__":
    main()
