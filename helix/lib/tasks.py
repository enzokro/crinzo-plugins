#!/usr/bin/env python3
"""Task operations helper for helix orchestrator.

This module provides CLI utilities for the orchestrator (SKILL.md) to:
- Parse builder output (DELIVERED/BLOCKED, UTILIZED)
- Close feedback loop after task completion
- Build lineage from completed tasks

Note: The actual TaskCreate/TaskList/TaskGet/TaskUpdate calls are made
directly by the orchestrator using Claude Code's native Task tools.
This module handles the helix-specific logic around those calls.

Usage from SKILL.md:
    # Parse builder output
    python3 $HELIX/lib/tasks.py parse-output "$builder_output"

    # Close feedback loop after completion
    python3 $HELIX/lib/tasks.py feedback \
        --utilized '["mem1"]' \
        --injected '["mem1", "mem2"]'
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple, Optional

try:
    from .memory import feedback as memory_feedback
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import feedback as memory_feedback


def parse_builder_output(output: str) -> dict:
    """Parse helix-builder output to extract status and utilized memories.

    Builder outputs in format:
        DELIVERED: <summary>
        UTILIZED:
        - memory-name: how it helped

    Or:
        BLOCKED: <reason>
        TRIED: <what was attempted>
        ERROR: <error message>
        UTILIZED:
        - memory-name: how it helped

    Args:
        output: Raw builder output string

    Returns:
        {
            "status": "delivered" | "blocked",
            "summary": "<delivered summary or blocked reason>",
            "tried": "<what was tried if blocked>",
            "error": "<error if any>",
            "utilized": ["memory-name-1", "memory-name-2"]
        }
    """
    result = {
        "status": "unknown",
        "summary": "",
        "tried": "",
        "error": "",
        "utilized": []
    }

    lines = output.strip().split("\n")

    # Find DELIVERED or BLOCKED
    for line in lines:
        if line.startswith("DELIVERED:"):
            result["status"] = "delivered"
            result["summary"] = line.replace("DELIVERED:", "").strip()
        elif line.startswith("BLOCKED:"):
            result["status"] = "blocked"
            result["summary"] = line.replace("BLOCKED:", "").strip()
        elif line.startswith("TRIED:"):
            result["tried"] = line.replace("TRIED:", "").strip()
        elif line.startswith("ERROR:"):
            result["error"] = line.replace("ERROR:", "").strip()

    # Extract UTILIZED memories
    # Format: "- memory-name: explanation" or just "- memory-name"
    in_utilized = False
    for line in lines:
        if line.strip() == "UTILIZED:" or line.strip().startswith("UTILIZED:"):
            in_utilized = True
            # Check for "UTILIZED: none" case
            if "none" in line.lower():
                in_utilized = False
            continue

        if in_utilized:
            if line.strip().startswith("-"):
                # Extract memory name (before colon if present)
                mem_part = line.strip()[1:].strip()
                mem_name = mem_part.split(":")[0].strip()
                if mem_name and mem_name.lower() != "none":
                    result["utilized"].append(mem_name)
            elif line.strip() and not line.startswith(" "):
                # End of UTILIZED section
                in_utilized = False

    return result


def close_feedback_loop(utilized: List[str], injected: List[str]) -> dict:
    """Close the feedback loop after task completion.

    This is THE critical learning mechanism. Memories that helped get
    their 'helped' count incremented. Memories that were injected but
    not utilized get their 'failed' count incremented.

    Args:
        utilized: Memory names the builder reported as actually helpful
        injected: Memory names that were injected into the builder context

    Returns:
        Result from memory.feedback()
    """
    try:
        return memory_feedback(utilized, injected)
    except Exception as e:
        return {"status": "error", "reason": str(e)}


def extract_task_id_mapping(planner_output: str) -> dict:
    """Extract seq -> taskId mapping from planner output.

    Planner should output mapping like:
        TASK_MAPPING:
        001 -> task-abc123
        002 -> task-def456

    Args:
        planner_output: Raw planner agent output

    Returns:
        {"001": "task-abc123", "002": "task-def456"}
    """
    mapping = {}

    in_mapping = False
    for line in planner_output.strip().split("\n"):
        if "TASK_MAPPING:" in line:
            in_mapping = True
            continue

        if in_mapping:
            if not line.strip():
                continue
            if "->" in line:
                parts = line.split("->")
                if len(parts) == 2:
                    seq = parts[0].strip()
                    task_id = parts[1].strip()
                    mapping[seq] = task_id
            elif not line.startswith(" ") and line.strip():
                # End of mapping section
                in_mapping = False

    return mapping


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix task operations helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse-output
    p = subparsers.add_parser("parse-output", help="Parse builder output")
    p.add_argument("output", help="Builder output string")

    # feedback
    p = subparsers.add_parser("feedback", help="Close feedback loop")
    p.add_argument("--utilized", required=True, help="JSON list of utilized memory names")
    p.add_argument("--injected", required=True, help="JSON list of injected memory names")

    # extract-mapping
    p = subparsers.add_parser("extract-mapping", help="Extract task ID mapping from planner output")
    p.add_argument("output", help="Planner output string")

    args = parser.parse_args()

    if args.command == "parse-output":
        result = parse_builder_output(args.output)
        print(json.dumps(result, indent=2))

    elif args.command == "feedback":
        utilized = json.loads(args.utilized)
        injected = json.loads(args.injected)
        result = close_feedback_loop(utilized, injected)
        print(json.dumps(result, indent=2))

    elif args.command == "extract-mapping":
        result = extract_task_id_mapping(args.output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
