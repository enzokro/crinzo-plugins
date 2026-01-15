#!/usr/bin/env python3
"""Campaign operations."""

from pathlib import Path
from datetime import datetime
import json
import argparse
import sys


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
    """
    if not CAMPAIGN_FILE.exists():
        raise ValueError("No active campaign")

    campaign = json.loads(CAMPAIGN_FILE.read_text())
    campaign["framework"] = plan.get("framework")
    campaign["tasks"] = [
        {
            "seq": t["seq"],
            "slug": t["slug"],
            "type": t.get("type", "BUILD"),
            "status": "pending"
        }
        for t in plan.get("tasks", [])
    ]
    CAMPAIGN_FILE.write_text(json.dumps(campaign, indent=2))


def update_task(seq: str, status: str) -> None:
    """Update task status.

    Args:
        seq: Task sequence number
        status: New status (pending, in_progress, complete, blocked)
    """
    if not CAMPAIGN_FILE.exists():
        raise ValueError("No active campaign")

    campaign = json.loads(CAMPAIGN_FILE.read_text())
    for task in campaign["tasks"]:
        if task["seq"] == seq:
            task["status"] = status
            task["updated_at"] = datetime.now().isoformat()
            break
    CAMPAIGN_FILE.write_text(json.dumps(campaign, indent=2))


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

    campaign = json.loads(CAMPAIGN_FILE.read_text())
    campaign["status"] = "complete"
    campaign["completed_at"] = datetime.now().isoformat()

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

    CAMPAIGN_FILE.write_text(json.dumps(campaign, indent=2))

    # Archive completed campaign
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    safe_ts = campaign["completed_at"].replace(":", "-").replace(".", "-")
    (ARCHIVE_DIR / f"{safe_ts}.json").write_text(json.dumps(campaign, indent=2))

    return campaign


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
