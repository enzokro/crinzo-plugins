#!/usr/bin/env python3
"""Parse structured fields from helix Task prompts.

Extracts key-value fields from agent prompts to enable hook-based
memory injection. Prompts use a simple format:

    FIELD_NAME: value
    FIELD_NAME: multi-line value continues
      until next FIELD_NAME or end

Supported fields by agent type:

Explorer:
    SCOPE: directory or area to explore
    FOCUS: specific aspect to focus on
    OBJECTIVE: user objective

Planner:
    OBJECTIVE: user objective
    EXPLORATION: JSON findings from explorers

Builder:
    TASK_ID: task identifier
    TASK: task subject
    OBJECTIVE: task description
    VERIFY: verification command
    RELEVANT_FILES: JSON list of files
    LINEAGE: JSON list of parent task summaries
    WARNING: systemic issue warning
    MEMORY_LIMIT: max memories to inject

Control:
    NO_INJECT: if "true", skip memory injection
"""

import json
import re
from typing import Any, Dict, List, Optional

# Fields that contain JSON values
JSON_FIELDS = {"RELEVANT_FILES", "LINEAGE", "EXPLORATION", "INJECTED_MEMORIES",
               "FAILURES_TO_AVOID", "PATTERNS_TO_APPLY", "CONVENTIONS_TO_FOLLOW",
               "RELATED_FACTS", "PARENT_DELIVERIES"}

# Fields that contain integer values
INT_FIELDS = {"MEMORY_LIMIT", "TASK_ID"}

# All recognized fields (uppercase)
RECOGNIZED_FIELDS = {
    "SCOPE", "FOCUS", "OBJECTIVE", "EXPLORATION",
    "TASK_ID", "TASK", "VERIFY", "RELEVANT_FILES",
    "LINEAGE", "WARNING", "MEMORY_LIMIT", "FRAMEWORK",
    "NO_INJECT", "INJECTED_MEMORIES", "FAILURES_TO_AVOID",
    "PATTERNS_TO_APPLY", "CONVENTIONS_TO_FOLLOW",
    "RELATED_FACTS", "PARENT_DELIVERIES"
}

# Pattern to match field lines: FIELD_NAME: value
FIELD_PATTERN = re.compile(r'^([A-Z][A-Z0-9_]*)\s*:\s*(.*)$', re.MULTILINE)


def parse_prompt(prompt: str) -> Dict[str, Any]:
    """Parse structured fields from a Task prompt.

    Args:
        prompt: Raw prompt string from Task tool_input

    Returns:
        Dict mapping field names (lowercase) to parsed values.
        JSON fields are parsed to Python objects.
        Integer fields are parsed to int.
        Unrecognized fields are ignored.

    Example:
        >>> parse_prompt("SCOPE: src/api/\\nOBJECTIVE: Find auth flow")
        {"scope": "src/api/", "objective": "Find auth flow"}
    """
    if not prompt:
        return {}

    result = {}
    lines = prompt.split('\n')
    current_field = None
    current_value_lines = []

    def commit_field():
        """Commit accumulated value to result."""
        nonlocal current_field, current_value_lines
        if current_field and current_field in RECOGNIZED_FIELDS:
            value = '\n'.join(current_value_lines).strip()
            key = current_field.lower()

            if current_field in JSON_FIELDS:
                try:
                    result[key] = json.loads(value)
                except json.JSONDecodeError:
                    result[key] = value  # Keep as string if not valid JSON
            elif current_field in INT_FIELDS:
                try:
                    result[key] = int(value)
                except ValueError:
                    result[key] = value  # Keep as string if not valid int
            else:
                result[key] = value

        current_field = None
        current_value_lines = []

    for line in lines:
        match = FIELD_PATTERN.match(line)
        if match:
            # New field starts - commit previous
            commit_field()
            field_name = match.group(1)
            field_value = match.group(2)
            current_field = field_name
            current_value_lines = [field_value]
        elif current_field:
            # Continuation line for current field
            current_value_lines.append(line)

    # Commit last field
    commit_field()

    return result


def detect_agent_type(prompt: str) -> Optional[str]:
    """Detect agent type from prompt structure.

    Args:
        prompt: Raw prompt string

    Returns:
        "explorer", "planner", "builder", or None
    """
    fields = parse_prompt(prompt)

    # Builder: has TASK_ID or TASK
    if "task_id" in fields or "task" in fields:
        return "builder"

    # Planner: has EXPLORATION
    if "exploration" in fields:
        return "planner"

    # Explorer: has SCOPE
    if "scope" in fields:
        return "explorer"

    return None


def extract_explorer_params(prompt: str) -> Dict[str, Any]:
    """Extract parameters for explorer context building.

    Args:
        prompt: Raw explorer prompt

    Returns:
        {"objective": str, "scope": str, "focus": str | None}
    """
    fields = parse_prompt(prompt)
    return {
        "objective": fields.get("objective", ""),
        "scope": fields.get("scope", ""),
        "focus": fields.get("focus"),
    }


def extract_planner_params(prompt: str) -> Dict[str, Any]:
    """Extract parameters for planner context building.

    Args:
        prompt: Raw planner prompt

    Returns:
        {"objective": str, "exploration": dict | None}
    """
    fields = parse_prompt(prompt)
    return {
        "objective": fields.get("objective", ""),
        "exploration": fields.get("exploration"),
    }


def extract_builder_params(prompt: str) -> Dict[str, Any]:
    """Extract parameters for builder context building.

    Args:
        prompt: Raw builder prompt

    Returns:
        Dict with task_id, task, objective, verify, relevant_files,
        lineage, warning, memory_limit
    """
    fields = parse_prompt(prompt)
    return {
        "task_id": fields.get("task_id"),
        "task": fields.get("task", ""),
        "objective": fields.get("objective", ""),
        "verify": fields.get("verify", ""),
        "relevant_files": fields.get("relevant_files", []),
        "lineage": fields.get("lineage", []),
        "warning": fields.get("warning"),
        "memory_limit": fields.get("memory_limit", 5),
        "framework": fields.get("framework"),
    }


def should_inject(prompt: str) -> bool:
    """Check if memory injection should occur.

    Args:
        prompt: Raw prompt string

    Returns:
        False if NO_INJECT: true, else True
    """
    fields = parse_prompt(prompt)
    no_inject = fields.get("no_inject", "")
    return str(no_inject).lower() not in ("true", "1", "yes")


def rebuild_prompt(fields: Dict[str, Any], preserve_order: List[str] = None) -> str:
    """Rebuild prompt from parsed fields.

    Args:
        fields: Dict mapping field names to values
        preserve_order: Optional list of field names in desired order

    Returns:
        Formatted prompt string
    """
    lines = []
    order = preserve_order or sorted(fields.keys())

    for key in order:
        if key not in fields:
            continue
        value = fields[key]
        field_name = key.upper()

        if isinstance(value, (dict, list)):
            value_str = json.dumps(value)
        else:
            value_str = str(value)

        lines.append(f"{field_name}: {value_str}")

    return '\n'.join(lines)


def inject_context_into_prompt(
    original_prompt: str,
    context_block: str,
    position: str = "prepend"
) -> str:
    """Inject context block into prompt.

    Args:
        original_prompt: Original prompt string
        context_block: Context to inject (formatted string)
        position: "prepend" (before prompt) or "append" (after)

    Returns:
        Modified prompt with context injected
    """
    if position == "prepend":
        return f"{context_block}\n\n---\n\n{original_prompt}"
    else:
        return f"{original_prompt}\n\n---\n\n{context_block}"


# CLI for testing
def _cli():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Parse structured fields from Task prompts")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse
    p = subparsers.add_parser("parse", help="Parse prompt and output fields as JSON")
    p.add_argument("--prompt", help="Prompt string (or read from stdin if not provided)")

    # detect-type
    p = subparsers.add_parser("detect-type", help="Detect agent type from prompt")
    p.add_argument("--prompt", help="Prompt string")

    # extract
    p = subparsers.add_parser("extract", help="Extract params for specific agent type")
    p.add_argument("--prompt", help="Prompt string")
    p.add_argument("--type", choices=["explorer", "planner", "builder"], required=True)

    args = parser.parse_args()

    # Read prompt from stdin if not provided
    prompt = args.prompt if hasattr(args, 'prompt') and args.prompt else sys.stdin.read()

    if args.command == "parse":
        result = parse_prompt(prompt)
        print(json.dumps(result, indent=2))

    elif args.command == "detect-type":
        result = detect_agent_type(prompt)
        print(result or "unknown")

    elif args.command == "extract":
        if args.type == "explorer":
            result = extract_explorer_params(prompt)
        elif args.type == "planner":
            result = extract_planner_params(prompt)
        else:
            result = extract_builder_params(prompt)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
