#!/usr/bin/env python3
"""Campaign operations."""

from pathlib import Path
from datetime import datetime
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
    if not CAMPAIGN_FILE.exists():
        return []

    campaign = json.loads(CAMPAIGN_FILE.read_text())
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
    if not CAMPAIGN_FILE.exists():
        return {"state": "none"}

    campaign = json.loads(CAMPAIGN_FILE.read_text())
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

        def do_update(campaign):
            nonlocal propagated
            for u in unreachable:
                seq = u["seq"]
                blocked_by = u["blocked_by"]
                for task in campaign["tasks"]:
                    if task["seq"] == seq:
                        task["status"] = "blocked"
                        task["blocked_by"] = blocked_by
                        task["updated_at"] = datetime.now().isoformat()
                        propagated.append(seq)
                        break

        atomic_json_update(CAMPAIGN_FILE, do_update)
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


def complete(summary: str = None) -> dict:
    """Complete campaign.

    Args:
        summary: Optional summary text (if None, computes dict summary)

    Returns:
        Final campaign dict with summary
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

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
