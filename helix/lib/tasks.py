#!/usr/bin/env python3
"""Task operations helper for helix orchestrator.

This module provides:
- parse_builder_output(): Parse DELIVERED/BLOCKED from builder output
- helix_task_state(): Derive canonical task state from dual status model

Note: The actual TaskCreate/TaskList/TaskGet/TaskUpdate calls are made
directly by the orchestrator using Claude Code's native Task tools.

ARCHITECTURAL PRINCIPLE: Single Source of Truth
-----------------------------------------------
Task state is tracked in TaskList metadata via 'helix_outcome' field.
Cycle detection is handled by dag_utils.py.

Usage from SKILL.md:
    python3 $HELIX/lib/tasks.py parse-output "$builder_output"
"""

import json
import sys
from pathlib import Path
from typing import List, Optional



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

    # Find DELIVERED or BLOCKED - FIRST match wins (fix for last-match bug)
    for line in lines:
        # Only set status on first match
        if result["status"] == "unknown":
            if line.startswith("DELIVERED:"):
                result["status"] = "delivered"
                result["summary"] = line.replace("DELIVERED:", "").strip()
            elif line.startswith("BLOCKED:"):
                result["status"] = "blocked"
                result["summary"] = line.replace("BLOCKED:", "").strip()

        # These can appear anywhere
        if line.startswith("TRIED:"):
            result["tried"] = line.replace("TRIED:", "").strip()
        elif line.startswith("ERROR:"):
            result["error"] = line.replace("ERROR:", "").strip()

    return result


def helix_task_state(task: dict) -> dict:
    """Derive canonical helix task state from task data.

    Interprets the dual status model:
    - Native `status`: Controls DAG execution (pending/in_progress/completed)
    - Helix `helix_outcome`: Captures semantic result (delivered/blocked/skipped)

    Args:
        task: Task data from TaskList/TaskGet

    Returns:
        {
            "executable": True if task can be executed (pending, unblocked),
            "finished": True if task is done (status=completed),
            "successful": True if finished AND helix_outcome=delivered,
            "outcome": "delivered"|"blocked"|"skipped"|"pending"|"in_progress",
            "blocks_dependents": True if this task failing blocks others
        }
    """
    status = task.get("status", "pending")
    helix_outcome = task.get("metadata", {}).get("helix_outcome")
    blocked_by = task.get("blockedBy", [])

    finished = status == "completed"
    executable = status == "pending" and len(blocked_by) == 0

    # Determine canonical outcome
    if finished:
        outcome = helix_outcome or "delivered"  # Default to delivered if not set
    else:
        outcome = status  # "pending" or "in_progress"

    successful = finished and outcome == "delivered"
    blocks_dependents = finished and outcome in ("blocked", "skipped")

    return {
        "executable": executable,
        "finished": finished,
        "successful": successful,
        "outcome": outcome,
        "blocks_dependents": blocks_dependents
    }


# CLI
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Helix task operations helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # parse-output
    p = subparsers.add_parser("parse-output", help="Parse builder output")
    p.add_argument("output", help="Builder output string")

    args = parser.parse_args()

    if args.command == "parse-output":
        result = parse_builder_output(args.output)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    _cli()
