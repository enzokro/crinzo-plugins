#!/usr/bin/env python3
"""Build loop utilities for helix orchestration.

Provides 7 CLI subcommands for the BUILD phase:
- wait-for-explorers: Poll for explorer result files
- wait-for-builders: Poll for builder task completions
- parent-deliveries: Collect parent deliveries for next wave
- detect-cycles: Find dependency loops in task DAG
- check-stalled: Detect build impasse
- get-ready: Identify unblocked tasks ready for execution
- status: Unified get-ready + check-stalled in one call
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.paths import get_helix_dir as _get_helix_dir

# ── Wait utilities ──


def _dedup_findings(findings: list) -> list:
    """Deduplicate findings by file path."""
    seen = set()
    unique = []
    for f in findings:
        key = f.get('file', str(f))
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


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

                return {
                    "completed": True,
                    "count": len(files),
                    "findings": _dedup_findings(all_findings),
                    "errors": errors if errors else None
                }

        time.sleep(poll_interval)

    # Timeout - return partial results
    partial_findings = []
    partial_files = list(results_dir.glob("*.json")) if results_dir.exists() else []
    for f in partial_files:
        try:
            data = json.loads(f.read_text())
            partial_findings.extend(data.get('findings', []))
        except Exception:
            pass

    return {
        "completed": False,
        "timed_out": True,
        "count": len(partial_files),
        "expected": expected_count,
        "findings": _dedup_findings(partial_findings)
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
                delivered = [e for e in found.values() if e.get("outcome") == "delivered"]
                blocked = [e for e in found.values() if e.get("outcome") == "blocked"]
                unknown = [e for e in found.values() if e.get("outcome") not in ("delivered", "blocked")]
                return {
                    "completed": True,
                    "count": len(found),
                    "delivered": delivered,
                    "blocked": blocked,
                    "unknown": unknown,
                    "all_delivered": len(blocked) == 0 and len(unknown) == 0,
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


def collect_parent_deliveries(
    wave_results: list,
    task_blockers: dict
) -> dict[str, str]:
    """Map next-wave task_id -> formatted PARENT_DELIVERIES from completed blockers.

    Args:
        wave_results: List of dicts with "task_id", "summary", "outcome" fields
        task_blockers: Dict mapping next-wave task_id -> list of blocker task_ids

    Returns: Dict mapping next-wave task_id -> formatted parent delivery string
    """
    # Index wave results by task_id (both "task-N" and "N" formats)
    result_by_id = {}
    for r in wave_results:
        tid = r.get("task_id")
        if tid:
            result_by_id[tid] = r
            # Normalize: index under both formats for cross-format lookup
            if tid.startswith("task-"):
                result_by_id[tid.removeprefix("task-")] = r
            else:
                result_by_id[f"task-{tid}"] = r

    deliveries = {}
    for next_task_id, blocker_ids in task_blockers.items():
        parts = []
        for bid in blocker_ids:
            result = result_by_id.get(bid)
            if result and result.get("outcome") == "delivered":
                summary = result.get("summary", "")[:200]
                if summary:
                    parts.append(f"[{bid}] {summary}")
        if parts:
            deliveries[next_task_id] = "\n".join(parts)

    return deliveries


# ── DAG utilities ──


def detect_cycles(dependencies: Dict[str, List[str]]) -> List[List[str]]:
    """Detect cycles in dependency graph using DFS.

    Args:
        dependencies: Dict mapping task_id -> list of blocker task_ids

    Returns:
        List of cycles found (each cycle is a list of task_ids)
    """
    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node: str, path: List[str]) -> None:
        if node in rec_stack:
            cycle_start = path.index(node)
            cycle = path[cycle_start:] + [node]
            cycles.append(cycle)
            return

        if node in visited:
            return

        visited.add(node)
        rec_stack.add(node)

        for neighbor in dependencies.get(node, []):
            dfs(neighbor, path + [node])

        rec_stack.discard(node)

    for node in dependencies:
        if node not in visited:
            dfs(node, [])

    return cycles


def _get_task_ids_by_outcome(all_tasks: List[Dict], outcome: str) -> List[str]:
    """Get task IDs with a specific helix_outcome.

    Derives state from TaskList metadata, not from parallel tracking.

    Args:
        all_tasks: List of task data from TaskList
        outcome: helix_outcome value to filter by ("delivered", "blocked", etc.)

    Returns:
        List of matching task IDs
    """
    return [
        t.get("id") for t in all_tasks
        if t.get("status") == "completed"
        and t.get("metadata", {}).get("helix_outcome") == outcome
    ]


def get_ready_tasks(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that are ready to execute.

    A task is ready if:
    - status == "pending"
    - all blockedBy tasks are completed with helix_outcome == "delivered"

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        List of task IDs ready for execution
    """
    delivered_ids = set(_get_task_ids_by_outcome(all_tasks, "delivered"))

    ready = []
    for task in all_tasks:
        if task.get("status") != "pending":
            continue

        blockers = task.get("blockedBy", [])
        if all(b in delivered_ids for b in blockers):
            ready.append(task.get("id"))

    return ready


def check_stalled(all_tasks: List[Dict], ready: List[str] = None,
                   pending: List[Dict] = None) -> Tuple[bool, Optional[Dict]]:
    """Check if build is stalled.

    Stalled = pending tasks exist but none are ready
    (all are blocked by BLOCKED tasks)

    Args:
        all_tasks: List of task data from TaskList
        ready: Precomputed ready task IDs (avoids recomputation)
        pending: Precomputed pending tasks (avoids recomputation)

    Returns:
        (is_stalled, stall_info)
    """
    if pending is None:
        pending = [t for t in all_tasks if t.get("status") == "pending"]
    if not pending:
        return False, None

    if ready is None:
        ready = get_ready_tasks(all_tasks)
    if ready:
        return False, None

    # Stalled - analyze why
    blocked_ids = set(_get_task_ids_by_outcome(all_tasks, "blocked"))
    blocked_by_blocked = []

    for task in pending:
        blockers = task.get("blockedBy", [])
        blocked_blockers = [b for b in blockers if b in blocked_ids]
        if blocked_blockers:
            blocked_by_blocked.append({
                "task_id": task.get("id"),
                "subject": task.get("subject"),
                "blocked_by": blocked_blockers
            })

    return True, {
        "pending_count": len(pending),
        "blocked_by_blocked": blocked_by_blocked
    }


def build_status(all_tasks: List[Dict]) -> Dict:
    """Unified build status: ready tasks + stall detection in one call.

    Returns:
        Dict with ready, ready_count, stalled, stall_info, pending_count
    """
    ready = get_ready_tasks(all_tasks)
    pending = [t for t in all_tasks if t.get("status") == "pending"]
    stalled = bool(pending and not ready)
    stall_info = None
    if stalled:
        _, stall_info = check_stalled(all_tasks, ready=ready, pending=pending)
    return {
        "ready": ready,
        "ready_count": len(ready),
        "stalled": stalled,
        "stall_info": stall_info,
        "pending_count": len(pending),
    }


# ── CLI ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Helix build loop utilities")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # wait-for-explorers
    p = subparsers.add_parser("wait-for-explorers")
    p.add_argument("--count", type=int, required=True)
    p.add_argument("--helix-dir")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--poll-interval", type=float, default=2.0)

    # wait-for-builders
    p = subparsers.add_parser("wait-for-builders")
    p.add_argument("--task-ids", required=True)
    p.add_argument("--helix-dir")
    p.add_argument("--timeout", type=float, default=300.0)
    p.add_argument("--poll-interval", type=float, default=2.0)

    # parent-deliveries
    p = subparsers.add_parser("parent-deliveries")
    p.add_argument("--results", required=True)
    p.add_argument("--blockers", required=True)

    # detect-cycles
    p = subparsers.add_parser("detect-cycles")
    p.add_argument("--dependencies", required=True)

    # check-stalled
    p = subparsers.add_parser("check-stalled")
    p.add_argument("--tasks", required=True)

    # get-ready
    p = subparsers.add_parser("get-ready")
    p.add_argument("--tasks", required=True)

    # status (unified: get-ready + check-stalled)
    p = subparsers.add_parser("status")
    p.add_argument("--tasks", required=True)

    args = parser.parse_args()

    if args.cmd == "wait-for-explorers":
        result = wait_for_explorer_results(args.count, args.helix_dir, args.timeout, args.poll_interval)
        print(json.dumps(result))
    elif args.cmd == "wait-for-builders":
        task_ids = [t.strip() for t in args.task_ids.split(",")]
        result = wait_for_builder_results(task_ids, args.helix_dir, args.timeout, args.poll_interval)
        print(json.dumps(result))
    elif args.cmd == "parent-deliveries":
        results = json.loads(args.results)
        blockers = json.loads(args.blockers)
        deliveries = collect_parent_deliveries(results, blockers)
        print(json.dumps(deliveries))
    elif args.cmd == "detect-cycles":
        deps = json.loads(args.dependencies)
        cycles = detect_cycles(deps)
        print(json.dumps({"cycles": cycles, "has_cycles": len(cycles) > 0}))
    elif args.cmd == "check-stalled":
        tasks = json.loads(args.tasks)
        is_stalled, info = check_stalled(tasks)
        print(json.dumps({"stalled": is_stalled, "info": info}))
    elif args.cmd == "get-ready":
        tasks = json.loads(args.tasks)
        ready = get_ready_tasks(tasks)
        print(json.dumps({"ready": ready, "count": len(ready)}))
    elif args.cmd == "status":
        tasks = json.loads(args.tasks)
        print(json.dumps(build_status(tasks)))
