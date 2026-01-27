#!/usr/bin/env python3
"""Wait-polling utilities for agent completion detection.

The output_file from Task(..., run_in_background=True) IS the wait primitive:
- Exists immediately when agent spawns
- Grows as agent works (JSONL)
- Contains completion markers
- Can be watched with grep (~0 context cost)

Pattern: SPAWN -> WATCH (grep output_file) -> RETRIEVE (TaskGet/TaskList)

Code surfaces facts. SKILL.md decides actions.
"""

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# Completion markers by agent type
MARKERS: Dict[str, List[str]] = {
    "builder": ["DELIVERED:", "BLOCKED:"],
    "explorer": ['"status":'],
    "planner": ["PLAN_COMPLETE:", "ERROR:"],
}


@dataclass
class WaitResult:
    """Result of waiting for agent completion."""
    completed: bool
    marker: Optional[str] = None
    content: Optional[str] = None
    timed_out: bool = False
    error: Optional[str] = None


def detect_completion(output_file: str, agent_type: str) -> Optional[Tuple[str, str]]:
    """Check if output_file contains completion marker.

    Uses grep subprocess for zero-context scanning.

    Args:
        output_file: Path to agent's JSONL output file
        agent_type: One of "builder", "explorer", "planner"

    Returns:
        (marker, content) if completed, None otherwise
    """
    if agent_type not in MARKERS:
        raise ValueError(f"Unknown agent type: {agent_type}. Expected one of: {list(MARKERS.keys())}")

    path = Path(output_file)
    if not path.exists():
        return None

    markers = MARKERS[agent_type]

    for marker in markers:
        try:
            # Use grep for efficient scanning without loading file into Python
            result = subprocess.run(
                ["grep", "-l", marker, str(path)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Found marker - extract the line containing it
                content_result = subprocess.run(
                    ["grep", marker, str(path)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                return (marker, content_result.stdout.strip())
        except subprocess.TimeoutExpired:
            continue
        except Exception:
            continue

    return None


def wait_for_completion(
    output_file: str,
    agent_type: str,
    timeout_sec: float = 300.0,
    poll_interval: float = 1.0
) -> WaitResult:
    """Wait for agent completion by polling output file.

    Args:
        output_file: Path to agent's JSONL output file
        agent_type: One of "builder", "explorer", "planner"
        timeout_sec: Maximum wait time in seconds
        poll_interval: Seconds between polls

    Returns:
        WaitResult with completion status and content
    """
    if agent_type not in MARKERS:
        return WaitResult(
            completed=False,
            error=f"Unknown agent type: {agent_type}. Expected one of: {list(MARKERS.keys())}"
        )

    start = time.time()

    while time.time() - start < timeout_sec:
        result = detect_completion(output_file, agent_type)
        if result:
            marker, content = result
            return WaitResult(
                completed=True,
                marker=marker,
                content=content
            )
        time.sleep(poll_interval)

    return WaitResult(
        completed=False,
        timed_out=True
    )


def get_completion_content(output_file: str, agent_type: str) -> Optional[dict]:
    """Extract structured completion content from output file.

    For explorers: Extracts the JSON block with status field
    For builders: Extracts DELIVERED/BLOCKED line content
    For planners: Extracts PLAN_COMPLETE or ERROR content

    Args:
        output_file: Path to agent's JSONL output file
        agent_type: One of "builder", "explorer", "planner"

    Returns:
        Parsed content dict or None if not completed
    """
    result = detect_completion(output_file, agent_type)
    if not result:
        return None

    marker, content = result

    if agent_type == "builder":
        # Parse DELIVERED: summary or BLOCKED: reason
        if "DELIVERED:" in content:
            return {"outcome": "delivered", "summary": content.split("DELIVERED:", 1)[1].strip()}
        elif "BLOCKED:" in content:
            return {"outcome": "blocked", "reason": content.split("BLOCKED:", 1)[1].strip()}

    elif agent_type == "explorer":
        # Extract JSON from the line
        try:
            # Find JSON object in content
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
        except json.JSONDecodeError:
            pass

    elif agent_type == "planner":
        if "PLAN_COMPLETE:" in content:
            return {"status": "complete", "detail": content.split("PLAN_COMPLETE:", 1)[1].strip()}
        elif "ERROR:" in content:
            return {"status": "error", "detail": content.split("ERROR:", 1)[1].strip()}

    return {"raw": content}


def get_last_json_block(output_file: str) -> Optional[dict]:
    """Extract the last JSON block from output file.

    Useful for explorers whose full findings are in the last JSON output.

    Args:
        output_file: Path to agent's JSONL output file

    Returns:
        Parsed JSON dict or None
    """
    path = Path(output_file)
    if not path.exists():
        return None

    try:
        # Read file and find last JSON block
        content = path.read_text()

        # Find last complete JSON object
        last_json = None
        depth = 0
        start = -1

        for i, char in enumerate(content):
            if char == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        last_json = json.loads(content[start:i+1])
                    except json.JSONDecodeError:
                        pass
                    start = -1

        return last_json
    except Exception:
        return None


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Helix wait-polling utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # check command - instant check, no waiting
    p_check = subparsers.add_parser("check", help="Check if agent completed (instant)")
    p_check.add_argument("--output-file", required=True, help="Path to agent output file")
    p_check.add_argument("--agent-type", required=True, choices=list(MARKERS.keys()),
                         help="Agent type for marker detection")

    # wait command - poll until completion or timeout
    p_wait = subparsers.add_parser("wait", help="Wait for agent completion")
    p_wait.add_argument("--output-file", required=True, help="Path to agent output file")
    p_wait.add_argument("--agent-type", required=True, choices=list(MARKERS.keys()),
                        help="Agent type for marker detection")
    p_wait.add_argument("--timeout", type=float, default=300.0, help="Timeout in seconds")
    p_wait.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")

    # extract command - get structured content from completed output
    p_extract = subparsers.add_parser("extract", help="Extract completion content")
    p_extract.add_argument("--output-file", required=True, help="Path to agent output file")
    p_extract.add_argument("--agent-type", required=True, choices=list(MARKERS.keys()),
                           help="Agent type for content extraction")

    # last-json command - get last JSON block (for explorer results)
    p_json = subparsers.add_parser("last-json", help="Extract last JSON block from output")
    p_json.add_argument("--output-file", required=True, help="Path to agent output file")

    args = parser.parse_args()

    if args.cmd == "check":
        result = detect_completion(args.output_file, args.agent_type)
        if result:
            marker, content = result
            print(json.dumps({"completed": True, "marker": marker, "content": content}))
        else:
            print(json.dumps({"completed": False}))

    elif args.cmd == "wait":
        result = wait_for_completion(
            args.output_file,
            args.agent_type,
            timeout_sec=args.timeout,
            poll_interval=args.poll_interval
        )
        print(json.dumps({
            "completed": result.completed,
            "marker": result.marker,
            "content": result.content,
            "timed_out": result.timed_out,
            "error": result.error
        }))

    elif args.cmd == "extract":
        content = get_completion_content(args.output_file, args.agent_type)
        if content:
            print(json.dumps({"extracted": True, "content": content}))
        else:
            print(json.dumps({"extracted": False}))

    elif args.cmd == "last-json":
        content = get_last_json_block(args.output_file)
        if content:
            print(json.dumps({"found": True, "content": content}))
        else:
            print(json.dumps({"found": False}))
