#!/usr/bin/env python3
"""Campaign operations with request-scoped caching."""

from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
import json
import argparse
import sys

# Support both standalone execution and module import
try:
    from lib.atomicfile import atomic_json_update
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from atomicfile import atomic_json_update


CAMPAIGN_FILE = Path(".ftl/campaign.json")
ARCHIVE_DIR = Path(".ftl/archive")
EXPLORATION_FILE = Path(".ftl/exploration.json")

# Request-scoped cache for campaign data
_cache = {
    "campaign": None,
    "mtime": None,
    "dirty": False,
}


def _load_cached(path: Path = CAMPAIGN_FILE) -> dict:
    """Load campaign with mtime-based cache validation.

    Returns cached data if file hasn't changed, otherwise reloads.
    """
    if not path.exists():
        _cache["campaign"] = None
        _cache["mtime"] = None
        return None

    current_mtime = path.stat().st_mtime
    if _cache["campaign"] is not None and _cache["mtime"] == current_mtime:
        return _cache["campaign"]

    _cache["campaign"] = json.loads(path.read_text())
    _cache["mtime"] = current_mtime
    return _cache["campaign"]


def _invalidate_cache():
    """Invalidate the cache after writes."""
    _cache["campaign"] = None
    _cache["mtime"] = None


@contextmanager
def campaign_session():
    """Context manager for batched campaign operations.

    Within a session, reads are cached and writes are batched.
    On exit, all pending updates are written atomically.

    Example:
        with campaign_session():
            update_task("001", "complete")
            update_task("002", "complete")
            # Single atomic write on exit
    """
    global _cache
    _cache["dirty"] = False
    try:
        yield
    finally:
        _invalidate_cache()


def create(objective: str, framework: str = None) -> dict:
    """Create new campaign.

    Args:
        objective: Campaign objective
        framework: Optional framework name

    Returns:
        Campaign dict
    """
    campaign = {
        "objective": objective,
        "framework": framework,
        "created_at": datetime.now().isoformat(),
        "status": "active",
        "tasks": [],
    }
    CAMPAIGN_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAMPAIGN_FILE.write_text(json.dumps(campaign, indent=2))
    return campaign


def add_tasks(plan: dict) -> None:
    """Add tasks from planner output.

    Args:
        plan: Plan dict with tasks[]

    Raises:
        ValueError: If no active campaign or cycle detected in dependencies
    """
    if not CAMPAIGN_FILE.exists():
        raise ValueError("No active campaign")

    tasks = plan.get("tasks", [])

    # Detect cycles before registering
    cycle = _detect_cycle(tasks)
    if cycle:
        cycle_str = " → ".join(str(s) for s in cycle)
        raise ValueError(f"Cycle detected in task dependencies: {cycle_str}")

    def do_update(campaign):
        campaign["framework"] = plan.get("framework")
        campaign["tasks"] = [
            {
                "seq": t["seq"],
                "slug": t["slug"],
                "type": t.get("type", "BUILD"),
                "depends": t.get("depends", "none"),  # Store for DAG scheduling
                "status": "pending"
            }
            for t in tasks
        ]

    atomic_json_update(CAMPAIGN_FILE, do_update)


def _normalize_seq(seq) -> int | str:
    """Normalize seq to int for comparison (handles '001' -> 1)."""
    try:
        return int(seq)
    except (ValueError, TypeError):
        return seq


def _get_deps(task: dict) -> list:
    """Extract normalized dependency list from task."""
    depends = task.get("depends", "none")
    if depends == "none" or depends is None:
        return []
    if isinstance(depends, str):
        return [_normalize_seq(depends)]
    return [_normalize_seq(d) for d in depends if d and d != "none"]


def _detect_cycle(tasks: list) -> list | None:
    """Detect cycle in task dependencies using DFS.

    Args:
        tasks: List of task dicts with seq and depends

    Returns:
        List of seqs forming cycle, or None if acyclic
    """
    # Build adjacency: task -> dependencies
    task_seqs = {_normalize_seq(t["seq"]) for t in tasks}
    deps = {_normalize_seq(t["seq"]): _get_deps(t) for t in tasks}

    visited = set()
    path = []
    path_set = set()

    def dfs(seq):
        if seq in path_set:
            # Found cycle - extract it
            cycle_start = path.index(seq)
            return path[cycle_start:] + [seq]
        if seq in visited:
            return None

        path.append(seq)
        path_set.add(seq)

        for dep in deps.get(seq, []):
            if dep in task_seqs:  # Only check deps within our task set
                result = dfs(dep)
                if result:
                    return result

        path.pop()
        path_set.remove(seq)
        visited.add(seq)
        return None

    for seq in task_seqs:
        if seq not in visited:
            result = dfs(seq)
            if result:
                return result

    return None


def update_task(seq: int | str, status: str) -> None:
    """Update task status.

    Args:
        seq: Task sequence number (int or string, e.g., 1, "1", "001")
        status: New status (pending, in_progress, complete, blocked)
    """
    if not CAMPAIGN_FILE.exists():
        raise ValueError("No active campaign")

    seq_normalized = _normalize_seq(seq)

    def do_update(campaign):
        for task in campaign["tasks"]:
            if _normalize_seq(task["seq"]) == seq_normalized:
                task["status"] = status
                task["updated_at"] = datetime.now().isoformat()
                break

    atomic_json_update(CAMPAIGN_FILE, do_update)
    _invalidate_cache()  # Invalidate cache after write


def next_task() -> dict | None:
    """Get next pending task.

    Returns:
        Task dict or None if no pending tasks
    """
    if not CAMPAIGN_FILE.exists():
        return None

    campaign = json.loads(CAMPAIGN_FILE.read_text())
    for task in campaign.get("tasks", []):
        if task.get("status") == "pending":
            return task
    return None


def ready_tasks() -> list[dict]:
    """Get all tasks ready for execution (pending with all dependencies complete).

    This enables DAG-based parallel execution: tasks whose dependencies are
    all complete can run simultaneously.

    Returns:
        List of task dicts ready for parallel execution
    """
    campaign = _load_cached()
    if campaign is None:
        return []

    tasks = campaign.get("tasks", [])

    # Build set of completed task seqs (normalized to int for comparison)
    completed_seqs = {
        _normalize_seq(t["seq"])
        for t in tasks
        if t.get("status") == "complete"
    }

    ready = []
    for task in tasks:
        if task.get("status") != "pending":
            continue

        depends = task.get("depends", "none")

        # Normalize depends to list
        if depends == "none" or depends is None:
            deps_list = []
        elif isinstance(depends, str):
            deps_list = [depends]
        else:
            deps_list = depends

        # Check if all dependencies are complete
        all_deps_complete = all(
            _normalize_seq(dep) in completed_seqs
            for dep in deps_list
        )

        if all_deps_complete:
            ready.append(task)

    return ready


def cascade_status() -> dict:
    """Detect if campaign is stuck due to blocked parent cascade.

    Returns:
        {
            "state": "none" | "complete" | "in_progress" | "stuck" | "all_blocked",
            "ready": int,
            "pending": int,
            "complete": int,
            "blocked": int,
            "unreachable": [{"seq": "002", "blocked_by": ["001"]}, ...]
        }
    """
    campaign = _load_cached()
    if campaign is None:
        return {"state": "none"}

    tasks = campaign.get("tasks", [])

    if not tasks:
        return {"state": "complete", "ready": 0, "pending": 0, "complete": 0, "blocked": 0, "unreachable": []}

    # Count by status
    counts = {
        "complete": sum(1 for t in tasks if t.get("status") == "complete"),
        "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
    }

    ready = ready_tasks()
    counts["ready"] = len(ready)

    # If we have ready tasks, we're in progress
    if ready:
        return {"state": "in_progress", **counts, "unreachable": []}

    # If no pending tasks, we're complete
    if counts["pending"] == 0:
        return {"state": "complete", **counts, "unreachable": []}

    # No ready tasks but pending exist - check for cascade
    blocked_seqs = {
        _normalize_seq(t["seq"])
        for t in tasks
        if t.get("status") == "blocked"
    }

    unreachable = []
    for t in tasks:
        if t.get("status") != "pending":
            continue

        deps = _get_deps(t)
        blocking_parents = [str(d) for d in deps if d in blocked_seqs]

        if blocking_parents:
            unreachable.append({
                "seq": t["seq"],
                "blocked_by": blocking_parents
            })

    if unreachable:
        return {"state": "stuck", **counts, "unreachable": unreachable}

    # Pending but not unreachable - shouldn't happen in valid DAG
    return {"state": "all_blocked", **counts, "unreachable": []}


def propagate_blocks() -> list:
    """Mark all unreachable tasks as blocked due to parent cascade.

    This allows the campaign to complete gracefully when some branches
    are blocked while others succeed. Loops until full cascade is propagated.

    Uses batched updates - all unreachable tasks in each iteration are
    updated in a single atomic write.

    Returns:
        List of task seqs that were marked blocked
    """
    all_propagated = []

    # Loop until no more unreachable tasks
    while True:
        cs = cascade_status()
        if cs.get("state") != "stuck":
            break

        unreachable = cs.get("unreachable", [])
        if not unreachable:
            break

        propagated = []

        # Build lookup for batch update
        unreachable_map = {u["seq"]: u["blocked_by"] for u in unreachable}

        def do_update(campaign):
            nonlocal propagated
            now = datetime.now().isoformat()
            for task in campaign["tasks"]:
                if task["seq"] in unreachable_map:
                    task["status"] = "blocked"
                    task["blocked_by"] = unreachable_map[task["seq"]]
                    task["updated_at"] = now
                    propagated.append(task["seq"])

        atomic_json_update(CAMPAIGN_FILE, do_update)
        _invalidate_cache()  # Invalidate cache after write
        all_propagated.extend(propagated)

    return all_propagated


def status() -> dict:
    """Get campaign status.

    Returns:
        Campaign dict or {"status": "none"} if no campaign
    """
    if not CAMPAIGN_FILE.exists():
        return {"status": "none"}
    return json.loads(CAMPAIGN_FILE.read_text())


def complete(summary: str = None, patterns_extracted: list = None) -> dict:
    """Complete campaign.

    Args:
        summary: Optional summary text (if None, computes dict summary)
        patterns_extracted: Optional list of pattern names extracted during this campaign

    Returns:
        Final campaign dict with summary and fingerprint
    """
    if not CAMPAIGN_FILE.exists():
        raise ValueError("No active campaign")

    completed_at = datetime.now().isoformat()
    result_campaign = {}

    def do_update(campaign):
        nonlocal result_campaign
        campaign["status"] = "complete"
        campaign["completed_at"] = completed_at

        # Calculate summary
        if summary is not None:
            campaign["summary"] = summary
        else:
            tasks = campaign.get("tasks", [])
            campaign["summary"] = {
                "total": len(tasks),
                "complete": sum(1 for t in tasks if t.get("status") == "complete"),
                "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
            }

        # Generate and store fingerprint for similarity matching
        campaign["fingerprint"] = fingerprint(campaign)

        # Store patterns extracted during this campaign (for transfer learning)
        if patterns_extracted:
            campaign["patterns_extracted"] = patterns_extracted

        # Store copy for archiving
        result_campaign = dict(campaign)

    atomic_json_update(CAMPAIGN_FILE, do_update)

    # Archive completed campaign
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = completed_at.replace(":", "-").replace(".", "-")
    (ARCHIVE_DIR / f"{safe_ts}.json").write_text(json.dumps(result_campaign, indent=2))

    return result_campaign


def history() -> dict:
    """Get archived campaign history.

    Returns:
        Dict with archives list containing objective, completed_at, summary
    """
    archives = []
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):
            campaign = json.loads(f.read_text())
            archives.append({
                "objective": campaign.get("objective"),
                "completed_at": campaign.get("completed_at"),
                "summary": campaign.get("summary"),
            })
    return {"archives": archives}


def export_history(output_file: str, start_date: str = None, end_date: str = None) -> dict:
    """Export campaign history to JSON file with optional date filtering.

    Args:
        output_file: Path to output JSON file
        start_date: Optional start date (YYYY-MM-DD format)
        end_date: Optional end date (YYYY-MM-DD format)

    Returns:
        Dict with campaigns list
    """
    campaigns = []
    if ARCHIVE_DIR.exists():
        for f in sorted(ARCHIVE_DIR.glob("*.json"), reverse=True):
            campaign = json.loads(f.read_text())
            completed_at = campaign.get("completed_at", "")

            # Extract date portion (YYYY-MM-DD) from ISO timestamp
            if completed_at:
                campaign_date = completed_at[:10]
            else:
                campaign_date = ""

            # Apply date filters
            if start_date and campaign_date < start_date:
                continue
            if end_date and campaign_date > end_date:
                continue

            campaigns.append(campaign)

    result = {"campaigns": campaigns}

    # Write to output file
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2))

    return result


def active() -> dict | None:
    """Get active campaign or None.

    Returns:
        Campaign dict if active, else None
    """
    if not CAMPAIGN_FILE.exists():
        return None
    campaign = json.loads(CAMPAIGN_FILE.read_text())
    if campaign.get("status") == "active":
        return campaign
    return None


def fingerprint(campaign: dict = None) -> dict:
    """Generate a fingerprint for campaign similarity matching.

    Fingerprint includes:
    - framework: The detected framework
    - task_count: Number of tasks
    - task_types: Set of task types (SPEC, BUILD)
    - delta_files: Sorted list of files being modified
    - objective_hash: Short hash of objective for quick comparison

    Args:
        campaign: Campaign dict (if None, loads active campaign)

    Returns:
        Fingerprint dict
    """
    if campaign is None:
        campaign = status()
        if campaign.get("status") == "none":
            return {}

    tasks = campaign.get("tasks", [])

    # Collect delta files from exploration if available
    delta_files = []
    if EXPLORATION_FILE.exists():
        try:
            exploration = json.loads(EXPLORATION_FILE.read_text())
            delta = exploration.get("delta", {})
            candidates = delta.get("candidates", [])
            delta_files = sorted(set(c.get("file", "") for c in candidates if c.get("file")))
        except (json.JSONDecodeError, KeyError):
            pass

    # Hash objective for quick comparison
    import hashlib
    objective = campaign.get("objective", "")
    obj_hash = hashlib.md5(objective.encode()).hexdigest()[:8]

    return {
        "framework": campaign.get("framework", "none"),
        "task_count": len(tasks),
        "task_types": sorted(set(t.get("type", "BUILD") for t in tasks)),
        "delta_files": delta_files[:20],  # Limit to 20 files
        "objective_hash": obj_hash,
        "objective_preview": objective[:100],
    }


def _embed_text(text: str) -> tuple | None:
    """Get embedding for text (lazy import)."""
    try:
        from embeddings import embed
        return embed(text)
    except ImportError:
        return None


def _cosine_similarity(vec1: tuple, vec2: tuple) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0
    try:
        import numpy as np
        v1, v2 = np.array(vec1), np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    except ImportError:
        return 0.0


def find_similar(
    current_fingerprint: dict = None,
    threshold: float = 0.6,
    max_results: int = 5
) -> list:
    """Find campaigns similar to the current one.

    Similarity is based on:
    - Framework match (required)
    - Objective embedding similarity
    - Delta file overlap

    Args:
        current_fingerprint: Fingerprint to compare (if None, uses active campaign)
        threshold: Minimum similarity score (0.0-1.0)
        max_results: Maximum number of results

    Returns:
        List of {"archive": str, "similarity": float, "fingerprint": dict, "outcome": str}
    """
    if current_fingerprint is None:
        current_fingerprint = fingerprint()

    if not current_fingerprint:
        return []

    current_framework = current_fingerprint.get("framework", "none")
    current_objective = current_fingerprint.get("objective_preview", "")
    current_delta = set(current_fingerprint.get("delta_files", []))
    current_embedding = _embed_text(current_objective)

    results = []

    if not ARCHIVE_DIR.exists():
        return []

    for archive_path in ARCHIVE_DIR.glob("*.json"):
        try:
            archived = json.loads(archive_path.read_text())
        except (json.JSONDecodeError, IOError):
            continue

        arch_fingerprint = archived.get("fingerprint", {})
        if not arch_fingerprint:
            # Legacy archive without fingerprint - generate one
            arch_fingerprint = {
                "framework": archived.get("framework", "none"),
                "task_count": len(archived.get("tasks", [])),
                "objective_preview": archived.get("objective", "")[:100],
            }

        # Framework must match (or both be "none")
        arch_framework = arch_fingerprint.get("framework", "none")
        if current_framework != "none" and arch_framework != current_framework:
            continue

        # Calculate similarity
        similarity = 0.0

        # Objective embedding similarity (weight: 0.6)
        arch_objective = arch_fingerprint.get("objective_preview", archived.get("objective", "")[:100])
        if current_embedding:
            arch_embedding = _embed_text(arch_objective)
            if arch_embedding:
                similarity += 0.6 * _cosine_similarity(current_embedding, arch_embedding)
        else:
            # Fallback to string comparison
            from difflib import SequenceMatcher
            similarity += 0.6 * SequenceMatcher(None, current_objective.lower(), arch_objective.lower()).ratio()

        # Delta file overlap (weight: 0.3)
        arch_delta = set(arch_fingerprint.get("delta_files", []))
        if current_delta and arch_delta:
            overlap = len(current_delta & arch_delta) / max(len(current_delta | arch_delta), 1)
            similarity += 0.3 * overlap

        # Task count similarity (weight: 0.1)
        current_tasks = current_fingerprint.get("task_count", 0)
        arch_tasks = arch_fingerprint.get("task_count", 0)
        if current_tasks > 0 and arch_tasks > 0:
            task_sim = 1.0 - abs(current_tasks - arch_tasks) / max(current_tasks, arch_tasks)
            similarity += 0.1 * task_sim

        if similarity >= threshold:
            # Determine outcome
            summary = archived.get("summary", {})
            if isinstance(summary, dict):
                total = summary.get("total", 0)
                complete = summary.get("complete", 0)
                outcome = "complete" if complete == total else "partial"
            else:
                outcome = "complete"

            results.append({
                "archive": archive_path.stem,
                "similarity": round(similarity, 3),
                "fingerprint": arch_fingerprint,
                "outcome": outcome,
                "objective": archived.get("objective", "")[:100],
                "patterns_from": archived.get("patterns_extracted", []),
            })

    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:max_results]


def main():
    parser = argparse.ArgumentParser(description="FTL campaign operations")
    subparsers = parser.add_subparsers(dest="command")

    # create command
    c = subparsers.add_parser("create", help="Create new campaign")
    c.add_argument("objective", help="Campaign objective")
    c.add_argument("--framework", help="Framework name")

    # add-tasks command
    at = subparsers.add_parser("add-tasks", help="Add tasks from plan (stdin)")

    # update-task command
    ut = subparsers.add_parser("update-task", help="Update task status")
    ut.add_argument("seq", help="Task sequence number")
    ut.add_argument("status", help="New status")

    # next-task command
    subparsers.add_parser("next-task", help="Get next pending task")

    # ready-tasks command
    subparsers.add_parser("ready-tasks", help="Get all tasks ready for parallel execution")

    # cascade-status command
    subparsers.add_parser("cascade-status", help="Check if campaign is stuck due to blocked cascade")

    # propagate-blocks command
    subparsers.add_parser("propagate-blocks", help="Mark unreachable tasks as blocked")

    # status command
    subparsers.add_parser("status", help="Get campaign status")

    # complete command
    comp = subparsers.add_parser("complete", help="Complete campaign")
    comp.add_argument("--summary", help="Summary text")

    # active command
    subparsers.add_parser("active", help="Check if campaign is active")

    # history command
    subparsers.add_parser("history", help="List archived campaigns")

    # export command
    exp = subparsers.add_parser("export", help="Export campaign history to file")
    exp.add_argument("output_file", help="Output JSON file path")
    exp.add_argument("--start", dest="start", help="Start date (YYYY-MM-DD)")
    exp.add_argument("--end", dest="end", help="End date (YYYY-MM-DD)")

    # fingerprint command
    subparsers.add_parser("fingerprint", help="Generate fingerprint for current campaign")

    # find-similar command
    sim = subparsers.add_parser("find-similar", help="Find similar archived campaigns")
    sim.add_argument("--threshold", type=float, default=0.6, help="Similarity threshold (0.0-1.0)")
    sim.add_argument("--max", type=int, default=5, help="Maximum results")

    args = parser.parse_args()

    if args.command == "create":
        result = create(args.objective, args.framework)
        print(json.dumps(result, indent=2))

    elif args.command == "add-tasks":
        plan = json.load(sys.stdin)
        add_tasks(plan)
        print("Tasks added")

    elif args.command == "update-task":
        update_task(args.seq, args.status)
        print(f"Task {args.seq} → {args.status}")

    elif args.command == "next-task":
        task = next_task()
        if task:
            print(json.dumps(task, indent=2))
        else:
            print("null")

    elif args.command == "ready-tasks":
        tasks = ready_tasks()
        print(json.dumps(tasks, indent=2))

    elif args.command == "cascade-status":
        result = cascade_status()
        print(json.dumps(result, indent=2))

    elif args.command == "propagate-blocks":
        propagated = propagate_blocks()
        if propagated:
            print(f"Propagated blocks to: {', '.join(propagated)}")
        else:
            print("No blocks to propagate")

    elif args.command == "status":
        result = status()
        print(json.dumps(result, indent=2))

    elif args.command == "complete":
        result = complete(args.summary)
        print(json.dumps(result, indent=2))

    elif args.command == "active":
        result = active()
        if result:
            print(json.dumps(result, indent=2))
        else:
            print("null")

    elif args.command == "history":
        result = history()
        print(json.dumps(result, indent=2))

    elif args.command == "export":
        result = export_history(args.output_file, args.start, args.end)
        print(json.dumps(result, indent=2))

    elif args.command == "fingerprint":
        result = fingerprint()
        print(json.dumps(result, indent=2))

    elif args.command == "find-similar":
        result = find_similar(threshold=args.threshold, max_results=args.max)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
