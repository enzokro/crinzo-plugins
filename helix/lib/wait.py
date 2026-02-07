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

NEVER use TaskOutput - dumps 70KB+ into context.
"""

import json
import time
from pathlib import Path
from typing import List, Optional

from lib.paths import get_helix_dir as _get_helix_dir


def _parse_task_status(status_file: Path, task_set: set) -> dict:
    """Parse task-status.jsonl for matching task IDs.

    Returns: dict mapping task_id -> entry
    """
    found = {}
    for line in status_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            tid = entry.get("task_id")
            if tid in task_set:
                found[tid] = entry
        except json.JSONDecodeError:
            continue
    return found


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
        results_dir = _get_helix_dir() / "explorer-results"

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


def wait_for_builder_results(
    task_ids: List[str],
    helix_dir: Optional[str] = None,
    timeout_sec: float = 300.0,
    poll_interval: float = 2.0
) -> dict:
    """Wait for builder task completions in task-status.jsonl.

    SubagentStop hook writes builder outcomes to .helix/task-status.jsonl.
    This function waits until all specified task_ids have entries.

    Args:
        task_ids: List of task IDs to wait for
        helix_dir: Path to .helix directory (defaults to cwd/.helix)
        timeout_sec: Maximum wait time in seconds
        poll_interval: Seconds between polls

    Returns:
        Dict with completed tasks grouped by outcome
    """
    if helix_dir:
        status_file = Path(helix_dir) / "task-status.jsonl"
    else:
        status_file = _get_helix_dir() / "task-status.jsonl"

    task_set = set(task_ids)
    start = time.time()

    while time.time() - start < timeout_sec:
        if status_file.exists():
            found = _parse_task_status(status_file, task_set)

            if task_set <= set(found.keys()):
                # All tasks found — pass through insight field for wave synthesis
                delivered = [e for e in found.values() if e.get("outcome") == "delivered"]
                blocked = [e for e in found.values() if e.get("outcome") == "blocked"]
                unknown = [e for e in found.values() if e.get("outcome") not in ("delivered", "blocked")]
                insights_emitted = sum(1 for e in found.values() if e.get("insight"))
                return {
                    "completed": True,
                    "count": len(found),
                    "delivered": delivered,
                    "blocked": blocked,
                    "unknown": unknown,
                    "all_delivered": len(blocked) == 0 and len(unknown) == 0,
                    "insights_emitted": insights_emitted
                }

        time.sleep(poll_interval)

    # Timeout - return partial results
    partial = {}
    if status_file.exists():
        partial = _parse_task_status(status_file, task_set)

    missing = task_set - set(partial.keys())
    return {
        "completed": False,
        "timed_out": True,
        "found": list(partial.values()),
        "missing": list(missing),
        "expected": list(task_ids)
    }


# CLI interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Helix wait-polling utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # wait-for-explorers command - wait for explorer result files
    p_explorers = subparsers.add_parser("wait-for-explorers",
                                         help="Wait for explorer result files written by SubagentStop hook")
    p_explorers.add_argument("--count", type=int, required=True,
                              help="Expected number of explorer results")
    p_explorers.add_argument("--helix-dir", help="Path to .helix directory (default: cwd/.helix)")
    p_explorers.add_argument("--timeout", type=float, default=300.0, help="Timeout in seconds")
    p_explorers.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")

    # wait-for-builders command - wait for builder task completions
    p_builders = subparsers.add_parser("wait-for-builders",
                                        help="Wait for builder task completions in task-status.jsonl")
    p_builders.add_argument("--task-ids", required=True,
                             help="Comma-separated list of task IDs to wait for")
    p_builders.add_argument("--helix-dir", help="Path to .helix directory (default: cwd/.helix)")
    p_builders.add_argument("--timeout", type=float, default=300.0, help="Timeout in seconds")
    p_builders.add_argument("--poll-interval", type=float, default=2.0, help="Poll interval in seconds")

    args = parser.parse_args()

    if args.cmd == "wait-for-explorers":
        result = wait_for_explorer_results(
            expected_count=args.count,
            helix_dir=args.helix_dir,
            timeout_sec=args.timeout,
            poll_interval=args.poll_interval
        )
        print(json.dumps(result))

    elif args.cmd == "wait-for-builders":
        task_ids = [t.strip() for t in args.task_ids.split(",")]
        result = wait_for_builder_results(
            task_ids=task_ids,
            helix_dir=args.helix_dir,
            timeout_sec=args.timeout,
            poll_interval=args.poll_interval
        )
        print(json.dumps(result))
