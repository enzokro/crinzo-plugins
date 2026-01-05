#!/usr/bin/env python3
"""forge - Campaign orchestration and session coordination."""

import json
import os
import sys
import re
import hashlib
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

FORGE_DIR = ".ftl"
CAMPAIGNS_DIR = "campaigns"
WORKSPACE_DIR = "workspace"

# Required fields for valid campaign schema
REQUIRED_CAMPAIGN_FIELDS = [
    "id", "objective", "started", "session", "status", "tasks",
    "precedent_used", "patterns_emerged", "signals_given",
    "revisions", "critic_verdicts"
]


def validate_campaign_schema(campaign: dict) -> None:
    """Validate campaign has required fields. Raises ValueError if invalid."""
    missing = [f for f in REQUIRED_CAMPAIGN_FIELDS if f not in campaign]
    if missing:
        raise ValueError(f"Invalid campaign schema - missing: {', '.join(missing)}")


def ensure_forge_dir(base: Path = Path(".")) -> Path:
    """Ensure .ftl directory structure exists."""
    forge = base / FORGE_DIR
    (forge / CAMPAIGNS_DIR / "active").mkdir(parents=True, exist_ok=True)
    (forge / CAMPAIGNS_DIR / "complete").mkdir(parents=True, exist_ok=True)
    return forge


def generate_session_id() -> str:
    """Generate short session ID."""
    return hashlib.md5(str(time.time()).encode()).hexdigest()[:8]


def slugify(text: str) -> str:
    """Convert text to slug."""
    slug = "-".join(text.lower().split()[:4])
    return "".join(c if c.isalnum() or c == "-" else "" for c in slug)


# --- Campaign Management ---

def create_campaign(objective: str, base: Path = Path(".")) -> dict:
    """Create new campaign."""
    forge = ensure_forge_dir(base)
    slug = slugify(objective)

    campaign = {
        "id": slug,
        "objective": objective,
        "started": datetime.utcnow().isoformat() + "Z",
        "session": generate_session_id(),
        "status": "active",
        "tasks": [],
        "precedent_used": [],
        "patterns_emerged": [],
        "signals_given": [],
        "revisions": 0,
        "critic_verdicts": []
    }

    path = forge / CAMPAIGNS_DIR / "active" / f"{slug}.json"
    path.write_text(json.dumps(campaign, indent=2))

    return campaign


def load_active_campaign(base: Path = Path(".")) -> Optional[dict]:
    """Load most recent active campaign."""
    forge = base / FORGE_DIR
    active_dir = forge / CAMPAIGNS_DIR / "active"

    if not active_dir.exists():
        return None

    campaigns = sorted(
        active_dir.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    if not campaigns:
        return None

    campaign = json.loads(campaigns[0].read_text())
    validate_campaign_schema(campaign)
    return campaign


def load_campaign_by_id(campaign_id: str, base: Path = Path(".")) -> Optional[dict]:
    """Load campaign by ID."""
    forge = base / FORGE_DIR

    # Check active first
    path = forge / CAMPAIGNS_DIR / "active" / f"{campaign_id}.json"
    if path.exists():
        campaign = json.loads(path.read_text())
        validate_campaign_schema(campaign)
        return campaign

    # Check complete
    path = forge / CAMPAIGNS_DIR / "complete" / f"{campaign_id}.json"
    if path.exists():
        campaign = json.loads(path.read_text())
        validate_campaign_schema(campaign)
        return campaign

    return None


def update_campaign(campaign: dict, base: Path = Path(".")) -> None:
    """Update campaign file."""
    forge = ensure_forge_dir(base)
    path = forge / CAMPAIGNS_DIR / "active" / f"{campaign['id']}.json"
    path.write_text(json.dumps(campaign, indent=2))


def complete_campaign(campaign: dict, base: Path = Path(".")) -> None:
    """Move campaign to complete."""
    forge = ensure_forge_dir(base)

    campaign["status"] = "complete"
    campaign["completed"] = datetime.utcnow().isoformat() + "Z"

    src = forge / CAMPAIGNS_DIR / "active" / f"{campaign['id']}.json"
    dst = forge / CAMPAIGNS_DIR / "complete" / f"{campaign['id']}.json"

    dst.write_text(json.dumps(campaign, indent=2))
    if src.exists():
        src.unlink()


def add_task_to_campaign(campaign: dict, seq: str, slug: str,
                         delta: str = "", verify: str = "", depends: str = "",
                         base: Path = Path(".")) -> None:
    """Add task to campaign."""
    task = {
        "seq": seq,
        "slug": slug,
        "status": "pending"
    }
    if delta:
        task["delta"] = delta
    if verify:
        task["verify"] = verify
    if depends:
        task["depends"] = depends
    campaign["tasks"].append(task)
    update_campaign(campaign, base)


def parse_planner_output(text: str) -> list:
    """Parse planner markdown output into task list.

    Expected format:
    ### Tasks

    1. **slug**: description
       Delta: src/file.ts
       Depends: none
       Done when: observable
       Verify: command
    """
    tasks = []

    # Find Tasks section
    lines = text.split('\n')
    in_tasks = False
    current_task = None

    for line in lines:
        # Start of Tasks section
        if line.strip().startswith('### Tasks'):
            in_tasks = True
            continue

        # Next section ends Tasks
        if in_tasks and line.strip().startswith('### '):
            break

        if not in_tasks:
            continue

        # New task line: "1. **slug**: description"
        task_match = re.match(r'^\d+\.\s+\*\*([^*]+)\*\*:\s*(.+)', line.strip())
        if task_match:
            if current_task:
                tasks.append(current_task)
            current_task = {
                'slug': task_match.group(1).strip(),
                'description': task_match.group(2).strip(),
                'delta': '',
                'verify': '',
                'depends': ''
            }
            continue

        # Task property lines
        if current_task and line.strip():
            prop_match = re.match(r'^(Delta|Verify|Depends|Done when):\s*(.+)', line.strip())
            if prop_match:
                key = prop_match.group(1).lower().replace(' ', '_')
                value = prop_match.group(2).strip()
                if key in ['delta', 'verify', 'depends']:
                    current_task[key] = value

    # Don't forget last task
    if current_task:
        tasks.append(current_task)

    return tasks


def add_tasks_from_plan(plan_text: str, base: Path = Path(".")) -> list:
    """Parse planner output and add tasks to active campaign."""
    campaign = load_active_campaign(base)
    if not campaign:
        raise ValueError("No active campaign")

    tasks = parse_planner_output(plan_text)
    if not tasks:
        raise ValueError("No tasks found in plan")

    added = []
    for i, task in enumerate(tasks, start=1):
        seq = f"{i:03d}"
        add_task_to_campaign(
            campaign, seq, task['slug'],
            delta=task.get('delta', ''),
            verify=task.get('verify', ''),
            depends=task.get('depends', ''),
            base=base
        )
        added.append(f"{seq}_{task['slug']}")

    return added


def update_task_status(campaign: dict, seq: str, status: str, base: Path = Path(".")) -> None:
    """Update task status in campaign."""
    for task in campaign["tasks"]:
        if task["seq"] == seq:
            task["status"] = status
            break
    update_campaign(campaign, base)


def add_precedent(campaign: dict, pattern: str, base: Path = Path(".")) -> None:
    """Record precedent used."""
    if pattern not in campaign["precedent_used"]:
        campaign["precedent_used"].append(pattern)
        update_campaign(campaign, base)


def add_pattern(campaign: dict, pattern: str, base: Path = Path(".")) -> None:
    """Record pattern emerged."""
    if pattern not in campaign["patterns_emerged"]:
        campaign["patterns_emerged"].append(pattern)
        update_campaign(campaign, base)


def add_signal(campaign: dict, pattern: str, signal: str, base: Path = Path(".")) -> None:
    """Record signal given."""
    campaign["signals_given"].append({
        "pattern": pattern,
        "signal": signal,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    update_campaign(campaign, base)


def add_verdict(campaign: dict, verdict: str, objections: list = None, base: Path = Path(".")) -> None:
    """Record critic verdict."""
    campaign["critic_verdicts"].append({
        "verdict": verdict,
        "objections": objections or [],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })
    update_campaign(campaign, base)


def increment_revision(campaign: dict, base: Path = Path(".")) -> int:
    """Increment revision count. Returns new count."""
    campaign["revisions"] = campaign.get("revisions", 0) + 1
    update_campaign(campaign, base)
    return campaign["revisions"]


# --- Workspace Coordination (Phase 1) ---

def get_active_workspace_files(base: Path = Path(".")) -> list:
    """Get active workspace files for coordination."""
    workspace = base / WORKSPACE_DIR
    if not workspace.exists():
        return []

    return sorted(workspace.glob("*_active*.md"))


def parse_workspace_filename(filename: str) -> Optional[dict]:
    """Parse workspace filename into components."""
    pattern = r'^(\d{3})_(.+?)_(active|complete|blocked)(?:_from-(\d{3}))?\.md$'
    match = re.match(pattern, filename)
    if not match:
        return None

    return {
        "seq": match.group(1),
        "slug": match.group(2),
        "status": match.group(3),
        "parent": match.group(4)
    }


def check_active_conflicts(campaign: dict, base: Path = Path(".")) -> list:
    """Check for active files that might conflict."""
    active_files = get_active_workspace_files(base)
    conflicts = []

    for path in active_files:
        parsed = parse_workspace_filename(path.name)
        if not parsed:
            continue

        # Check if this file belongs to our campaign
        is_ours = any(
            t["seq"] == parsed["seq"]
            for t in campaign.get("tasks", [])
        )

        if not is_ours:
            conflicts.append({
                "file": path.name,
                "seq": parsed["seq"],
                "slug": parsed["slug"]
            })

    return conflicts


def get_next_sequence(base: Path = Path(".")) -> str:
    """Get next available sequence number."""
    workspace = base / WORKSPACE_DIR
    if not workspace.exists():
        return "001"

    existing = []
    for path in workspace.glob("*.md"):
        parsed = parse_workspace_filename(path.name)
        if parsed:
            existing.append(int(parsed["seq"]))

    if not existing:
        return "001"

    return f"{max(existing) + 1:03d}"


# --- Synthesis ---

def load_synthesis(base: Path = Path(".")) -> dict:
    """Load synthesis data."""
    forge = base / FORGE_DIR
    path = forge / "synthesis.json"

    if not path.exists():
        return {
            "meta_patterns": [],
            "evolution": [],
            "updated": None
        }

    return json.loads(path.read_text())


def save_synthesis(synthesis: dict, base: Path = Path(".")) -> None:
    """Save synthesis data."""
    forge = ensure_forge_dir(base)
    path = forge / "synthesis.json"

    synthesis["updated"] = datetime.utcnow().isoformat() + "Z"
    path.write_text(json.dumps(synthesis, indent=2))


def get_all_campaigns(base: Path = Path(".")) -> list:
    """Get all campaigns (active and complete)."""
    forge = base / FORGE_DIR
    campaigns = []

    for subdir in ["active", "complete"]:
        dir_path = forge / CAMPAIGNS_DIR / subdir
        if dir_path.exists():
            for path in dir_path.glob("*.json"):
                campaigns.append(json.loads(path.read_text()))

    return campaigns


def aggregate_patterns(base: Path = Path(".")) -> dict:
    """Aggregate pattern usage across campaigns."""
    campaigns = get_all_campaigns(base)
    patterns = {}

    for campaign in campaigns:
        # Count pattern usage
        for pattern in campaign.get("patterns_emerged", []):
            if pattern not in patterns:
                patterns[pattern] = {"count": 0, "positive": 0, "negative": 0}
            patterns[pattern]["count"] += 1

        # Count signals
        for sig in campaign.get("signals_given", []):
            pattern = sig["pattern"]
            if pattern not in patterns:
                patterns[pattern] = {"count": 0, "positive": 0, "negative": 0}
            if sig["signal"] == "+":
                patterns[pattern]["positive"] += 1
            elif sig["signal"] == "-":
                patterns[pattern]["negative"] += 1

    return patterns


# --- Analysis (v2 - Scout support) ---

def get_pending_work(base: Path = Path(".")) -> list:
    """Get pending tasks from active campaign."""
    campaign = load_active_campaign(base)
    if not campaign:
        return []

    return [t for t in campaign.get("tasks", []) if t.get("status") == "pending"]


def get_negative_patterns(base: Path = Path(".")) -> list:
    """Get patterns with negative net signals."""
    # Import here to avoid circular dependency
    from context_graph import load_memory
    memory = load_memory(base)

    return [
        {"pattern": k, "net": v.get("net", 0)}
        for k, v in memory.get("patterns", {}).items()
        if v.get("net", 0) < 0
    ]


def get_synthesis_status(base: Path = Path(".")) -> dict:
    """Check if synthesis is needed."""
    forge = base / FORGE_DIR
    synthesis_path = forge / "synthesis.json"
    complete_dir = forge / CAMPAIGNS_DIR / "complete"

    complete_count = len(list(complete_dir.glob("*.json"))) if complete_dir.exists() else 0

    last_synthesis = None
    if synthesis_path.exists():
        synthesis = json.loads(synthesis_path.read_text())
        last_synthesis = synthesis.get("updated")

    return {
        "complete_campaigns": complete_count,
        "last_synthesis": last_synthesis,
        "needs_synthesis": complete_count >= 3 and not last_synthesis
    }


def get_stale_workspace_files(hours: int = 24, base: Path = Path(".")) -> list:
    """Get active workspace files older than threshold."""
    workspace = base / WORKSPACE_DIR
    if not workspace.exists():
        return []

    threshold = time.time() - (hours * 3600)
    stale = []

    for path in workspace.glob("*_active*.md"):
        if path.stat().st_mtime < threshold:
            age_hours = int((time.time() - path.stat().st_mtime) / 3600)
            stale.append({
                "file": path.name,
                "age_hours": age_hours
            })

    return stale


# --- Status ---

def get_status(base: Path = Path(".")) -> dict:
    """Get full forge status."""
    campaign = load_active_campaign(base)
    active_files = get_active_workspace_files(base)

    campaigns_dir = base / FORGE_DIR / CAMPAIGNS_DIR
    active_count = len(list((campaigns_dir / "active").glob("*.json"))) if (campaigns_dir / "active").exists() else 0
    complete_count = len(list((campaigns_dir / "complete").glob("*.json"))) if (campaigns_dir / "complete").exists() else 0

    return {
        "campaign": campaign,
        "active_workspace_files": [f.name for f in active_files],
        "campaigns_active": active_count,
        "campaigns_complete": complete_count
    }


# --- CLI ---

def main():
    import argparse

    parser = argparse.ArgumentParser(prog="forge")
    parser.add_argument("-b", "--base", type=Path, default=Path("."))

    sub = parser.add_subparsers(dest="cmd")

    # Campaign
    camp_p = sub.add_parser("campaign", help="Create or find campaign")
    camp_p.add_argument("objective", nargs="?")

    # Active
    sub.add_parser("active", help="Show active campaign")

    # Status
    sub.add_parser("status", help="Full status")

    # Next sequence
    sub.add_parser("next-seq", help="Get next sequence number")

    # Add task
    add_p = sub.add_parser("add-task", help="Add task to campaign")
    add_p.add_argument("seq")
    add_p.add_argument("slug")

    # Add tasks from planner output
    sub.add_parser("add-tasks-from-plan", help="Parse planner output (stdin) and add tasks")

    # Update task
    upd_p = sub.add_parser("update-task", help="Update task status")
    upd_p.add_argument("seq")
    upd_p.add_argument("status")

    # Complete campaign
    sub.add_parser("complete", help="Complete active campaign")

    # Aggregate patterns
    sub.add_parser("patterns", help="Aggregate pattern usage")

    # Check conflicts
    sub.add_parser("conflicts", help="Check for active file conflicts")

    # Add verdict
    verdict_p = sub.add_parser("add-verdict", help="Record critic verdict")
    verdict_p.add_argument("verdict", choices=["APPROVE", "OBJECT", "OVERRIDE"])

    # Increment revision
    sub.add_parser("revision", help="Increment revision count")

    # Scout analysis commands (v2)
    sub.add_parser("pending", help="Get pending tasks")
    sub.add_parser("negative-patterns", help="Get patterns with negative signals")
    sub.add_parser("synthesis-status", help="Check if synthesis needed")
    stale_p = sub.add_parser("stale-workspace", help="Get stale active files")
    stale_p.add_argument("hours", nargs="?", type=int, default=24)

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == "campaign":
        if args.objective:
            campaign = create_campaign(args.objective, args.base)
            print(json.dumps(campaign, indent=2))
        else:
            campaign = load_active_campaign(args.base)
            if campaign:
                print(json.dumps(campaign, indent=2))
            else:
                print("No active campaign")

    elif args.cmd == "active":
        campaign = load_active_campaign(args.base)
        if campaign:
            print(json.dumps(campaign, indent=2))
        else:
            print("No active campaign")

    elif args.cmd == "status":
        status = get_status(args.base)
        if status["campaign"]:
            c = status["campaign"]
            complete = sum(1 for t in c.get("tasks", []) if t.get("status") == "complete")
            total = len(c.get("tasks", []))
            print(f"Campaign: {c['id']} ({complete}/{total} tasks)")
            for t in c.get("tasks", []):
                marker = {"complete": "+", "active": "~", "blocked": "!"}.get(t.get("status"), " ")
                print(f"  [{marker}] {t.get('seq', '???')}_{t.get('slug', 'unknown')}")
        else:
            print("No active campaign")

        print(f"\nActive workspace files: {len(status['active_workspace_files'])}")
        for f in status['active_workspace_files']:
            print(f"  [~] {f}")

        print(f"\nCampaigns: {status['campaigns_active']} active, {status['campaigns_complete']} complete")

    elif args.cmd == "next-seq":
        seq = get_next_sequence(args.base)
        print(seq)

    elif args.cmd == "add-task":
        campaign = load_active_campaign(args.base)
        if campaign:
            add_task_to_campaign(campaign, args.seq, args.slug, base=args.base)
            print(f"Added task: {args.seq}_{args.slug}")
        else:
            print("No active campaign")

    elif args.cmd == "add-tasks-from-plan":
        try:
            plan_text = sys.stdin.read()
            added = add_tasks_from_plan(plan_text, args.base)
            print(f"Added {len(added)} tasks:")
            for task in added:
                print(f"  {task}")
        except ValueError as e:
            print(f"ERROR: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "update-task":
        campaign = load_active_campaign(args.base)
        if campaign:
            # ENFORCE workspace gate for completion
            if args.status == "complete":
                workspace = args.base / WORKSPACE_DIR
                pattern = f"{args.seq}_*_complete*.md"
                matches = list(workspace.glob(pattern))
                if not matches:
                    print(f"ERROR: Cannot mark complete - no workspace file", file=sys.stderr)
                    print(f"Expected: workspace/{pattern}", file=sys.stderr)
                    print(f"Tether must create workspace file before task can be marked complete.", file=sys.stderr)
                    sys.exit(1)
            update_task_status(campaign, args.seq, args.status, args.base)
            print(f"Updated task {args.seq}: {args.status}")
        else:
            print("No active campaign", file=sys.stderr)
            sys.exit(1)

    elif args.cmd == "complete":
        campaign = load_active_campaign(args.base)
        if campaign:
            complete_campaign(campaign, args.base)
            print(f"Completed campaign: {campaign['id']}")
        else:
            print("No active campaign")

    elif args.cmd == "patterns":
        patterns = aggregate_patterns(args.base)
        if patterns:
            print("Pattern usage:")
            for p, stats in sorted(patterns.items(), key=lambda x: -x[1]["count"]):
                net = stats["positive"] - stats["negative"]
                sign = "+" if net > 0 else ("-" if net < 0 else " ")
                print(f"  {p}: {stats['count']}x (net {sign}{abs(net)})")
        else:
            print("No patterns found")

    elif args.cmd == "conflicts":
        campaign = load_active_campaign(args.base)
        if campaign:
            conflicts = check_active_conflicts(campaign, args.base)
            if conflicts:
                print("Active files (potential conflicts):")
                for c in conflicts:
                    print(f"  {c['file']}")
            else:
                print("No conflicts detected")
        else:
            print("No active campaign")

    elif args.cmd == "add-verdict":
        campaign = load_active_campaign(args.base)
        if campaign:
            add_verdict(campaign, args.verdict, base=args.base)
            print(f"Recorded verdict: {args.verdict}")
        else:
            print("No active campaign")

    elif args.cmd == "revision":
        campaign = load_active_campaign(args.base)
        if campaign:
            count = increment_revision(campaign, args.base)
            print(f"Revision count: {count}")
        else:
            print("No active campaign")

    elif args.cmd == "pending":
        pending = get_pending_work(args.base)
        if pending:
            print("Pending tasks:")
            for t in pending:
                print(f"  {t.get('seq', '???')}_{t.get('slug', 'unknown')}")
        else:
            print("No pending tasks")

    elif args.cmd == "negative-patterns":
        negative = get_negative_patterns(args.base)
        if negative:
            print("Patterns with negative signals:")
            for p in sorted(negative, key=lambda x: x["net"]):
                print(f"  {p['pattern']}: net {p['net']}")
        else:
            print("No negative patterns")

    elif args.cmd == "synthesis-status":
        status = get_synthesis_status(args.base)
        print(f"Complete campaigns: {status['complete_campaigns']}")
        print(f"Last synthesis: {status['last_synthesis'] or 'never'}")
        print(f"Needs synthesis: {'yes' if status['needs_synthesis'] else 'no'}")

    elif args.cmd == "stale-workspace":
        stale = get_stale_workspace_files(args.hours, args.base)
        if stale:
            print(f"Active files older than {args.hours}h:")
            for s in stale:
                print(f"  {s['file']} ({s['age_hours']}h)")
        else:
            print("No stale active files")


if __name__ == "__main__":
    main()
