#!/usr/bin/env python3
"""Task operations helper for helix orchestrator.

This module provides CLI utilities for the orchestrator (SKILL.md) to:
- Parse builder output (DELIVERED/BLOCKED)
- Close feedback loop after task completion
- Build lineage from completed tasks

Note: The actual TaskCreate/TaskList/TaskGet/TaskUpdate calls are made
directly by the orchestrator using Claude Code's native Task tools.
This module handles the helix-specific logic around those calls.

ARCHITECTURAL PRINCIPLE: Single Source of Truth
-----------------------------------------------
Task state is tracked in TaskList metadata via 'helix_outcome' field.
Cycle detection is handled by orchestrator.py (canonical implementation).

Usage from SKILL.md:
    # Parse builder output
    python3 $HELIX/lib/tasks.py parse-output "$builder_output"

    # Close feedback loop after completion
    python3 $HELIX/lib/tasks.py feedback-verify \
        --task-id "task-123" \
        --verify-passed true \
        --injected '["mem1", "mem2"]'
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

try:
    from .memory import feedback_from_verification as memory_feedback_verify
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import feedback_from_verification as memory_feedback_verify


def parse_builder_output(output: str) -> dict:
    """Parse helix-builder output to extract status.

    Builder outputs in format:
        DELIVERED: <summary>

    Or:
        BLOCKED: <reason>
        TRIED: <what was attempted>
        ERROR: <error message>

    Args:
        output: Raw builder output string

    Returns:
        {
            "status": "delivered" | "blocked",
            "summary": "<delivered summary or blocked reason>",
            "tried": "<what was tried if blocked>",
            "error": "<error if any>"
        }
    """
    result = {
        "status": "unknown",
        "summary": "",
        "tried": "",
        "error": ""
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

    return result


def close_feedback_loop_verified(
    task_id: str,
    verify_passed: bool,
    injected: List[str]
) -> dict:
    """Close the feedback loop based on verification outcome.

    This is the preferred feedback mechanism. Instead of trusting builder
    self-reports about which memories helped, we use the objective
    verification command result as ground truth.

    Attribution logic:
        - verify_passed=True: All injected memories get partial credit (0.5)
        - verify_passed=False: No penalty to memories (unknown cause)

    This approach is:
        - Incorruptible: Builder can't game the system
        - Conservative: Partial credit acknowledges uncertainty
        - Safe: Failure doesn't punish memories unfairly

    Args:
        task_id: The task that completed
        verify_passed: Whether the verify command succeeded
        injected: Memory names that were injected into the builder context

    Returns:
        Result from memory.feedback_from_verification()
    """
    try:
        return memory_feedback_verify(
            task_id=task_id,
            verify_passed=verify_passed,
            injected=injected
        )
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

    # feedback-verify
    p = subparsers.add_parser("feedback-verify", help="Close feedback loop via verification")
    p.add_argument("--task-id", required=True, help="Task ID that completed")
    p.add_argument("--verify-passed", required=True, help="true/false - did verify command pass?")
    p.add_argument("--injected", required=True, help="JSON list of injected memory names")

    # extract-mapping
    p = subparsers.add_parser("extract-mapping", help="Extract task ID mapping from planner output")
    p.add_argument("output", help="Planner output string")

    args = parser.parse_args()

    if args.command == "parse-output":
        result = parse_builder_output(args.output)
        print(json.dumps(result, indent=2))

    elif args.command == "feedback-verify":
        verify_passed = args.verify_passed.lower() == "true"
        injected = json.loads(args.injected)
        result = close_feedback_loop_verified(
            task_id=args.task_id,
            verify_passed=verify_passed,
            injected=injected
        )
        print(json.dumps(result, indent=2))

    elif args.command == "extract-mapping":
        result = extract_task_id_mapping(args.output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
