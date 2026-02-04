#!/usr/bin/env python3
"""Memory injection hook for helix agents.

Called by PreToolUse hook on Task tool. Parses the prompt,
builds appropriate context based on agent type, and returns
an updatedInput with enriched prompt.

Also stores injection state for feedback attribution.

Usage (from pretool-task.sh):
    python3 "$HELIX/lib/hooks/inject_memory.py" < hook_input.json
"""

import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_parser import (
    parse_prompt,
    should_inject,
    inject_context_into_prompt,
    extract_explorer_params,
    extract_planner_params,
    extract_builder_params,
)
from context import (
    build_explorer_context,
    build_planner_context,
    build_context,
)


def get_helix_dir() -> Path:
    """Get .helix directory using ancestor search (consistent with db.connection).

    Walks up from cwd to find nearest .helix/ directory. This ensures
    injection-state files are written to the same location as the DB.
    """
    # Check env var first (if inherited from CLAUDE_ENV_FILE)
    project_dir = os.environ.get("HELIX_PROJECT_DIR")
    if project_dir:
        helix_dir = Path(project_dir) / ".helix"
        helix_dir.mkdir(exist_ok=True)
        return helix_dir

    # Ancestor search (mirrors db.connection._get_default_db_path)
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        helix_dir = parent / ".helix"
        if helix_dir.exists() and helix_dir.is_dir():
            return helix_dir

    # Fallback: create in cwd (greenfield case)
    helix_dir = cwd / ".helix"
    helix_dir.mkdir(exist_ok=True)
    return helix_dir


def get_injection_state_dir() -> Path:
    """Get injection state directory."""
    state_dir = get_helix_dir() / "injection-state"
    state_dir.mkdir(exist_ok=True)
    return state_dir


def store_injection_state(
    tool_use_id: str,
    agent_type: str,
    task_id: Optional[str],
    injected_memories: list,
) -> Path:
    """Store injection state for feedback attribution.

    Args:
        tool_use_id: Unique ID for this tool invocation
        agent_type: helix:helix-explorer, etc.
        task_id: Task ID if builder, else None
        injected_memories: List of memory names injected

    Returns:
        Path to state file
    """
    state_dir = get_injection_state_dir()
    state_file = state_dir / f"{tool_use_id}.json"

    state = {
        "tool_use_id": tool_use_id,
        "agent_type": agent_type,
        "task_id": task_id,
        "injected_memories": injected_memories,
        "injected_at": datetime.now(timezone.utc).isoformat(),
    }

    state_file.write_text(json.dumps(state, indent=2))
    return state_file


def format_explorer_context(ctx: dict) -> str:
    """Format explorer context as injectable block."""
    lines = ["# MEMORY CONTEXT (auto-injected)", ""]

    if ctx.get("known_facts"):
        lines.append("## Known Facts")
        for fact in ctx["known_facts"]:
            lines.append(f"- {fact}")
        lines.append("")

    if ctx.get("relevant_failures"):
        lines.append("## Relevant Failures")
        for failure in ctx["relevant_failures"]:
            lines.append(f"- {failure}")
        lines.append("")

    if not ctx.get("known_facts") and not ctx.get("relevant_failures"):
        lines.append("No relevant memories found for this scope.")
        lines.append("")

    return "\n".join(lines)


def format_planner_context(ctx: dict) -> str:
    """Format planner context as injectable block."""
    lines = ["# PROJECT CONTEXT (auto-injected)", ""]

    if ctx.get("decisions"):
        lines.append("## Prior Decisions")
        for dec in ctx["decisions"]:
            lines.append(f"- {dec}")
        lines.append("")

    if ctx.get("conventions"):
        lines.append("## Conventions")
        for conv in ctx["conventions"]:
            lines.append(f"- {conv}")
        lines.append("")

    if ctx.get("recent_evolution"):
        lines.append("## Recent Evolution")
        for evo in ctx["recent_evolution"]:
            lines.append(f"- {evo}")
        lines.append("")

    if not any([ctx.get("decisions"), ctx.get("conventions"), ctx.get("recent_evolution")]):
        lines.append("No relevant project context found.")
        lines.append("")

    return "\n".join(lines)


def format_builder_context(ctx: dict) -> str:
    """Format builder context - already formatted by build_context."""
    # build_context returns {"prompt": ..., "injected": ...}
    # The prompt already contains all the structured fields
    return ctx.get("prompt", "")


def inject_for_explorer(prompt: str, tool_use_id: str) -> Dict[str, Any]:
    """Inject memory context for explorer agent.

    Args:
        prompt: Original explorer prompt
        tool_use_id: Unique ID for tracking

    Returns:
        {"prompt": enriched_prompt, "injected": memory_names}
    """
    params = extract_explorer_params(prompt)

    # Build context from memory
    ctx = build_explorer_context(
        objective=params.get("objective", ""),
        scope=params.get("scope", ""),
        limit=5,
    )

    # Format and inject
    context_block = format_explorer_context(ctx)
    enriched = inject_context_into_prompt(prompt, context_block, position="prepend")

    return {
        "prompt": enriched,
        "injected": ctx.get("injected", []),
    }


def inject_for_planner(prompt: str, tool_use_id: str) -> Dict[str, Any]:
    """Inject memory context for planner agent.

    Args:
        prompt: Original planner prompt
        tool_use_id: Unique ID for tracking

    Returns:
        {"prompt": enriched_prompt, "injected": memory_names}
    """
    params = extract_planner_params(prompt)

    # Build context from memory
    ctx = build_planner_context(
        objective=params.get("objective", ""),
        limit=5,
    )

    # Format and inject
    context_block = format_planner_context(ctx)
    enriched = inject_context_into_prompt(prompt, context_block, position="prepend")

    return {
        "prompt": enriched,
        "injected": ctx.get("injected", []),
    }


def inject_for_builder(prompt: str, tool_use_id: str) -> Dict[str, Any]:
    """Inject memory context for builder agent.

    For builders, we reconstruct task_data from parsed prompt fields
    and call build_context which handles all the memory queries.

    Args:
        prompt: Original builder prompt
        tool_use_id: Unique ID for tracking

    Returns:
        {"prompt": enriched_prompt, "injected": memory_names}
    """
    params = extract_builder_params(prompt)

    # Reconstruct task_data format expected by build_context
    task_data = {
        "id": params.get("task_id"),
        "subject": params.get("task", ""),
        "description": params.get("objective", ""),
        "metadata": {
            "verify": params.get("verify", ""),
            "relevant_files": params.get("relevant_files", []),
            "framework": params.get("framework"),
        },
    }

    # Build context using existing function
    ctx = build_context(
        task_data=task_data,
        lineage=params.get("lineage", []),
        memory_limit=params.get("memory_limit", 5),
        warning=params.get("warning"),
    )

    # build_context returns a complete prompt, not a context block
    # For builders, we replace the prompt entirely
    return {
        "prompt": ctx.get("prompt", prompt),
        "injected": ctx.get("injected", []),
    }


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
            - {"decision": "block", "reason": "..."} to block
            - {"updatedInput": {...}} to modify
    """
    tool_name = hook_input.get("tool_name", "")
    if tool_name != "Task":
        return {}

    tool_input = hook_input.get("tool_input", {})
    subagent_type = tool_input.get("subagent_type", "")
    prompt = tool_input.get("prompt", "")
    tool_use_id = hook_input.get("tool_use_id", str(uuid.uuid4()))

    # Only process helix agents
    if not subagent_type.startswith("helix:helix-"):
        return {}

    # Check for NO_INJECT flag
    if not should_inject(prompt):
        return {}

    # Route to appropriate injector
    # Explorer runs its own recall() - hook injection is redundant
    agent_short = subagent_type.replace("helix:helix-", "")
    task_id = None

    if agent_short == "explorer":
        # Explorer prompts pass through unmodified - agent runs own recall()
        return {}
    elif agent_short == "planner":
        result = inject_for_planner(prompt, tool_use_id)
    elif agent_short == "builder":
        result = inject_for_builder(prompt, tool_use_id)
        # Extract task_id for builders
        params = extract_builder_params(prompt)
        task_id = params.get("task_id")
    else:
        # Unknown helix agent type
        return {}

    # Store injection state for feedback attribution
    if result.get("injected"):
        store_injection_state(
            tool_use_id=tool_use_id,
            agent_type=subagent_type,
            task_id=str(task_id) if task_id else None,
            injected_memories=result["injected"],
        )

    # Return updated input
    updated_input = dict(tool_input)
    updated_input["prompt"] = result["prompt"]

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
        # Invalid JSON input - let tool proceed unmodified
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        print("{}")

    except Exception as e:
        # Any other error - log but don't block
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        print("{}")


if __name__ == "__main__":
    main()
