#!/usr/bin/env python3
"""Build loop utilities for helix orchestration.

Provides 7 CLI subcommands for the BUILD phase:
- wait-for-explorers: Poll for explorer result files
- wait-for-builders: Poll for builder task completions
- synthesize: Detect convergent issues across wave results
- parent-deliveries: Collect parent deliveries for next wave
- detect-cycles: Find dependency loops in task DAG
- check-stalled: Detect build impasse
- get-ready: Identify unblocked tasks ready for execution

NEVER use TaskOutput — dumps 70KB+ into context.
"""

import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from lib.paths import get_helix_dir as _get_helix_dir

# ── Constants ──

CONVERGENCE_THRESHOLD = 0.65
MIN_CONVERGENT_COUNT = 2

# ── Wait utilities ──


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


# ── Wave synthesis ──


def _union_find_clusters(items: list, similarity_fn, threshold: float) -> list[list[int]]:
    """Union-find clustering based on pairwise similarity.

    Args:
        items: List of items to cluster
        similarity_fn: (item_a, item_b) -> float
        threshold: Minimum similarity to merge clusters

    Returns: List of clusters (each cluster is a list of indices)
    """
    n = len(items)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for i in range(n):
        for j in range(i + 1, n):
            if similarity_fn(items[i], items[j]) >= threshold:
                union(i, j)

    clusters = {}
    for i in range(n):
        root = find(i)
        clusters.setdefault(root, []).append(i)

    return list(clusters.values())


def synthesize_wave_warnings(
    wave_results: list,
    threshold: float = CONVERGENCE_THRESHOLD,
    min_count: int = MIN_CONVERGENT_COUNT
) -> list[str]:
    """Detect convergent issues across wave results and format as warnings.

    Args:
        wave_results: List of dicts with at least "summary" and optionally
                      "task_id", "insight", "outcome" fields
        threshold: Cosine similarity threshold for convergence detection
        min_count: Minimum cluster size to emit a warning

    Returns: List of WARNING strings for injection into next wave
    """
    # Lazy import: only load embeddings when this function is called
    from lib.memory.embeddings import embed, cosine

    # Filter to results with summaries
    summaries = []
    for r in wave_results:
        text = r.get("summary", "") or ""
        insight = r.get("insight", "") or ""
        combined = f"{text} {insight}".strip()
        if combined:
            summaries.append({"text": combined, "task_id": r.get("task_id", "?"), "result": r})

    if len(summaries) < min_count:
        return []

    # Embed all summaries
    embeddings = []
    valid = []
    for s in summaries:
        emb = embed(s["text"], is_query=False)
        if emb:
            embeddings.append(emb)
            valid.append(s)

    if len(valid) < min_count:
        return []

    # Cluster by similarity
    def sim_fn(a, b):
        return cosine(a, b)

    clusters = _union_find_clusters(embeddings, sim_fn, threshold)

    # Format warnings for convergent clusters
    warnings = []
    for cluster in clusters:
        if len(cluster) < min_count:
            continue

        # Build warning from cluster members
        task_ids = [valid[i]["task_id"] for i in cluster]
        texts = [valid[i]["text"][:150] for i in cluster]

        # Use first summary as representative, note all task IDs
        warning = (
            f"CONVERGENT ISSUE (tasks {', '.join(task_ids)}): "
            f"Multiple builders encountered similar issue. "
            f"Representative: {texts[0]}"
        )
        warnings.append(warning)

    return warnings


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
            try:
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                cycles.append(cycle)
            except ValueError:
                pass
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


def _get_completed_task_ids(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that completed successfully (delivered)."""
    return _get_task_ids_by_outcome(all_tasks, "delivered")


def _get_blocked_task_ids(all_tasks: List[Dict]) -> List[str]:
    """Get task IDs that were blocked."""
    return _get_task_ids_by_outcome(all_tasks, "blocked")


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
    ready = []

    # Build set of successfully completed task IDs
    completed_ids = set(_get_completed_task_ids(all_tasks))
    blocked_ids = set(_get_blocked_task_ids(all_tasks))

    for task in all_tasks:
        if task.get("status") != "pending":
            continue

        blockers = task.get("blockedBy", [])
        # All blockers must be completed AND not blocked
        all_blockers_done = all(
            b in completed_ids and b not in blocked_ids
            for b in blockers
        )

        if all_blockers_done:
            ready.append(task.get("id"))

    return ready


def check_stalled(all_tasks: List[Dict]) -> Tuple[bool, Optional[Dict]]:
    """Check if build is stalled.

    Stalled = pending tasks exist but none are ready
    (all are blocked by BLOCKED tasks)

    Args:
        all_tasks: List of task data from TaskList

    Returns:
        (is_stalled, stall_info)
    """
    pending = [t for t in all_tasks if t.get("status") == "pending"]
    if not pending:
        return False, None

    ready = get_ready_tasks(all_tasks)
    if ready:
        return False, None

    # Stalled - analyze why
    blocked_ids = set(_get_blocked_task_ids(all_tasks))
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

    # synthesize
    p = subparsers.add_parser("synthesize")
    p.add_argument("--results", required=True)
    p.add_argument("--threshold", type=float, default=CONVERGENCE_THRESHOLD)
    p.add_argument("--min-count", type=int, default=MIN_CONVERGENT_COUNT)

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

    args = parser.parse_args()

    if args.cmd == "wait-for-explorers":
        result = wait_for_explorer_results(args.count, args.helix_dir, args.timeout, args.poll_interval)
        print(json.dumps(result))
    elif args.cmd == "wait-for-builders":
        task_ids = [t.strip() for t in args.task_ids.split(",")]
        result = wait_for_builder_results(task_ids, args.helix_dir, args.timeout, args.poll_interval)
        print(json.dumps(result))
    elif args.cmd == "synthesize":
        results = json.loads(args.results)
        warnings = synthesize_wave_warnings(results, args.threshold, args.min_count)
        print(json.dumps({"warnings": warnings, "count": len(warnings)}))
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
