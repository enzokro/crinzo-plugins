#!/usr/bin/env python3
"""Wait utilities for helix agent results.

Preferred patterns (no TaskOutput, no context floods):

1. FOREGROUND agents (planner, single builder):
   - Task returns result directly
   - No waiting needed

2. BACKGROUND agents (explorers, parallel builders):
   - SubagentStop hook writes results to small files:
     - Explorers: .helix/explorer-results/{agent_id}.json (~500 bytes)
     - Builders: .helix/task-status.jsonl (~100 bytes per entry)
   - Use wait-for-explorers to wait and merge explorer findings

Legacy pattern (still supported for builder polling):
   SPAWN -> WATCH (output_file markers) -> RETRIEVE

NEVER use TaskOutput - dumps 70KB+ into context.
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
    """Check if output_file contains completion marker in ASSISTANT messages only.

    Parses JSONL and filters by role to avoid false positives from user prompts
    that may contain TASK_ID, DELIVERED, or BLOCKED keywords.

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

    try:
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                # Only check assistant messages
                role = entry.get('message', {}).get('role', entry.get('role', ''))
                if role != 'assistant':
                    continue

                content = entry.get('message', {}).get('content', '')
                if isinstance(content, list):
                    content = ' '.join(
                        c.get('text', '') for c in content
                        if isinstance(c, dict) and c.get('type') == 'text'
                    )

                for marker in markers:
                    if marker in str(content):
                        return (marker, str(content))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass

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


def wait_for_explorer_results(
    expected_count: int,
    helix_dir: Optional[str] = None,
    timeout_sec: float = 300.0,
    poll_interval: float = 2.0
) -> dict:
    """Wait for explorer result files and return merged findings.

    SubagentStop hook writes explorer findings to .helix/explorer-results/{agent_id}.json.
    This function waits for the expected number of files and merges them.

    Args:
        expected_count: Number of explorer results to wait for
        helix_dir: Path to .helix directory (defaults to cwd/.helix)
        timeout_sec: Maximum wait time in seconds
        poll_interval: Seconds between polls

    Returns:
        Dict with merged findings and metadata
    """
    if helix_dir:
        results_dir = Path(helix_dir) / "explorer-results"
    else:
        results_dir = Path.cwd() / ".helix" / "explorer-results"

    start = time.time()

    while time.time() - start < timeout_sec:
        if results_dir.exists():
            files = list(results_dir.glob("*.json"))
            if len(files) >= expected_count:
                # Merge all findings
                all_findings = []
                errors = []
                for f in files:
                    try:
                        data = json.loads(f.read_text())
                        findings = data.get('findings', [])
                        if findings:
                            all_findings.extend(findings)
                        elif data.get('status') == 'error':
                            errors.append(data.get('error', 'Unknown error'))
                    except Exception as e:
                        errors.append(f"Failed to parse {f.name}: {e}")

                # Dedupe by file path
                seen = set()
                unique_findings = []
                for f in all_findings:
                    key = f.get('file', str(f))
                    if key not in seen:
                        seen.add(key)
                        unique_findings.append(f)

                return {
                    "completed": True,
                    "count": len(files),
                    "findings": unique_findings,
                    "errors": errors if errors else None
                }

        time.sleep(poll_interval)

    # Timeout - return partial results
    partial_findings = []
    if results_dir.exists():
        for f in results_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                partial_findings.extend(data.get('findings', []))
            except:
                pass

    return {
        "completed": False,
        "timed_out": True,
        "count": len(list(results_dir.glob("*.json"))) if results_dir.exists() else 0,
        "expected": expected_count,
        "findings": partial_findings
    }


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

    # wait-for-explorers command - wait for explorer result files
    p_explorers = subparsers.add_parser("wait-for-explorers",
                                         help="Wait for explorer result files written by SubagentStop hook")
    p_explorers.add_argument("--count", type=int, required=True,
                              help="Expected number of explorer results")
    p_explorers.add_argument("--helix-dir", help="Path to .helix directory (default: cwd/.helix)")
    p_explorers.add_argument("--timeout", type=float, default=300.0, help="Timeout in seconds")
    p_explorers.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")

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

    elif args.cmd == "wait-for-explorers":
        result = wait_for_explorer_results(
            expected_count=args.count,
            helix_dir=args.helix_dir,
            timeout_sec=args.timeout,
            poll_interval=args.poll_interval
        )
        print(json.dumps(result))
