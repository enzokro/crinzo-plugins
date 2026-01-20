#!/usr/bin/env python3
"""Workspace operations with fastsql database backend.

Provides workspace lifecycle management, code context extraction,
and memory injection for builder agents.

API:
- create(plan, task_seq) -> list[dict]  # Returns workspace data dicts
- complete(path_or_id, delivered, utilized) -> dict  # Returns updated workspace
- block(path_or_id, reason) -> dict  # Returns updated workspace
Accepts both Path objects and workspace_id strings for backwards compatibility.
"""

from pathlib import Path
from datetime import datetime
import json
import argparse
import sys

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, Workspace, db_write_lock
    from lib.framework_registry import get_idioms
    from lib.plan import read as read_plan
except ImportError:
    from db import get_db, init_db, Workspace, db_write_lock
    from framework_registry import get_idioms
    from plan import read as read_plan


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


def _get_active_campaign():
    """Get active campaign from database."""
    db = _ensure_db()
    campaigns = db.t.campaign
    rows = list(campaigns.rows_where("status = ?", ["active"]))
    if rows:
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[0]
    return None


# =============================================================================
# Core Workspace Operations
# =============================================================================

def create(plan: dict, task_seq: str = None) -> list:
    """Create workspace records from plan.

    Args:
        plan: Plan dict with tasks[]
        task_seq: Optional specific task seq to create

    Returns:
        List of workspace dicts with workspace_id, status, etc.
    """
    db = _ensure_db()
    workspaces = db.t.workspace
    campaign = _get_active_campaign()

    if not campaign:
        return []

    # Get memory context
    memory_ctx = {"failures": [], "patterns": []}
    try:
        from lib.memory import get_context
        task_context = plan.get("objective", "")
        memory_ctx = get_context(
            objective=task_context if task_context else None,
            max_failures=5,
            max_patterns=3
        )
    except (ImportError, Exception) as e:
        import logging
        logging.warning(f"Failed to get memory context: {e}. Using empty prior_knowledge.")

    # Get sibling failures from blocked workspaces
    sibling_failures = get_sibling_failures(campaign["id"])
    memory_ctx["sibling_failures"] = sibling_failures

    created_workspaces = []
    tasks = plan.get("tasks", [])

    if task_seq:
        tasks = [t for t in tasks if t["seq"] == task_seq]

    for task in tasks:
        ws_id = f"{task['seq']}-{task['slug']}"

        # Use lock to protect duplicate check + insert (TOCTOU race prevention)
        with db_write_lock:
            # Check if workspace already exists FOR THIS CAMPAIGN
            existing = list(workspaces.rows_where(
                "workspace_id = ? AND campaign_id = ?",
                [ws_id, campaign["id"]]
            ))
            if existing:
                # Return existing workspace from current campaign
                created_workspaces.append(_ws_to_dict(existing[0]))
                continue

            # Check for stale workspace from old campaign
            stale = list(workspaces.rows_where("workspace_id = ?", [ws_id]))
            if stale:
                # Workspace exists but belongs to different campaign - error
                stale_campaign = stale[0].get("campaign_id")
                raise ValueError(
                    f"Workspace {ws_id} exists from campaign {stale_campaign}, "
                    f"cannot reuse for campaign {campaign['id']}. "
                    "Clear old workspaces or use unique task slugs."
                )

            # Build lineage from parent tasks
            lineage = _build_lineage(task.get("depends"), campaign["id"])

            # Extract code contexts for delta files
            code_contexts = []
            task_type = task.get("type", "BUILD")
            target_lines_map = task.get("target_lines", {})

            for delta in task.get("delta", []):
                delta_path = Path(delta)
                if delta_path.exists():
                    target_lines = target_lines_map.get(delta)
                    ctx = extract_code_context(
                        delta_path,
                        target_lines=target_lines,
                        task_type=task_type
                    )
                    if ctx:
                        code_contexts.append(ctx)

            # Get framework idioms
            framework = plan.get("framework")
            idioms = {}
            if framework and framework != "none":
                registry_idioms = get_idioms(framework)
                plan_idioms = plan.get("idioms", {})
                idioms = {
                    "required": registry_idioms.get("required") or plan_idioms.get("required", []),
                    "forbidden": registry_idioms.get("forbidden") or plan_idioms.get("forbidden", []),
                }

            # Get framework confidence
            framework_confidence = _get_framework_confidence()

            # Extract verify_source
            verify_source = task.get("verify_source")
            if not verify_source:
                verify_source = extract_verify_source(task.get("verify", ""))

            # Build workspace dict for validation
            ws_dict = {
                "id": ws_id,
                "status": "active",
                "delta": task.get("delta", []),
                "verify": task.get("verify", ""),
            }

            # Validate workspace before insert - FATAL on failure
            is_valid, missing = validate_workspace(ws_dict)
            if not is_valid:
                raise ValueError(f"Workspace {ws_id} validation failed: missing {missing}")

            # Insert workspace record
            now = datetime.now().isoformat()
            ws = Workspace(
                workspace_id=ws_id,
                campaign_id=campaign["id"],
                seq=task["seq"],
                slug=task["slug"],
                status="active",
                created_at=now,
                completed_at=None,
                blocked_at=None,
                objective=plan.get("objective", ""),
                delta=json.dumps(task.get("delta", [])),
                verify=task.get("verify", ""),
                verify_source=verify_source,
                budget=task.get("budget", 5),
                framework=framework,
                framework_confidence=framework_confidence,
                idioms=json.dumps(idioms),
                prior_knowledge=json.dumps(memory_ctx),
                lineage=json.dumps(lineage),
                delivered="",
                utilized_memories="[]",
                code_contexts=json.dumps(code_contexts),
                preflight=json.dumps(task.get("preflight", []))
            )

            result = workspaces.insert(ws)

            # Fetch inserted workspace to get all fields
            inserted = list(workspaces.rows_where("id = ?", [result.id]))[0]
            created_workspaces.append(_ws_to_dict(inserted))

    return created_workspaces


def complete(path_or_id, delivered: str, utilized_memories: list = None) -> dict:
    """Mark workspace complete.

    Args:
        path_or_id: Path to workspace or workspace_id string
        delivered: Summary of what was delivered
        utilized_memories: List of {"name": str, "type": str} that were helpful

    Returns:
        Updated workspace dict
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    # Handle both Path and workspace_id
    if isinstance(path_or_id, Path):
        workspace_id = _extract_workspace_id(path_or_id)
    elif isinstance(path_or_id, str):
        if "/" in path_or_id or path_or_id.endswith(".xml"):
            workspace_id = _extract_workspace_id(Path(path_or_id))
        else:
            workspace_id = path_or_id
    else:
        workspace_id = str(path_or_id)

    # Use lock to protect read-modify-write sequence
    with db_write_lock:
        rows = list(workspaces.rows_where("workspace_id = ?", [workspace_id]))

        if not rows:
            raise ValueError(f"Workspace not found: {workspace_id}")

        ws = rows[0]
        now = datetime.now().isoformat()

        workspaces.update({
            "status": "complete",
            "completed_at": now,
            "delivered": delivered,
            "utilized_memories": json.dumps(utilized_memories or [])
        }, ws["id"])

        # Fetch updated workspace
        updated = list(workspaces.rows_where("id = ?", [ws["id"]]))[0]

    return _ws_to_dict(updated)


def block(path_or_id, reason: str) -> dict:
    """Mark workspace blocked.

    Args:
        path_or_id: Path to workspace or workspace_id string
        reason: Why it was blocked

    Returns:
        Updated workspace dict
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    # Handle both Path and workspace_id
    if isinstance(path_or_id, Path):
        workspace_id = _extract_workspace_id(path_or_id)
    elif isinstance(path_or_id, str):
        if "/" in path_or_id or path_or_id.endswith(".xml"):
            workspace_id = _extract_workspace_id(Path(path_or_id))
        else:
            workspace_id = path_or_id
    else:
        workspace_id = str(path_or_id)

    # Use lock to protect read-modify-write sequence
    with db_write_lock:
        rows = list(workspaces.rows_where("workspace_id = ?", [workspace_id]))

        if not rows:
            raise ValueError(f"Workspace not found: {workspace_id}")

        ws = rows[0]
        now = datetime.now().isoformat()

        workspaces.update({
            "status": "blocked",
            "blocked_at": now,
            "delivered": f"BLOCKED: {reason}"
        }, ws["id"])

        # Fetch updated workspace
        updated = list(workspaces.rows_where("id = ?", [ws["id"]]))[0]

    return _ws_to_dict(updated)


def parse(path_or_id) -> dict:
    """Parse workspace to dict.

    Args:
        path_or_id: Path object, path string, or workspace_id string

    Returns:
        Workspace dict
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    # Handle various input types
    if isinstance(path_or_id, Path):
        workspace_id = _extract_workspace_id(path_or_id)
    elif isinstance(path_or_id, str):
        if "/" in path_or_id or path_or_id.endswith(".xml"):
            workspace_id = _extract_workspace_id(Path(path_or_id))
        else:
            workspace_id = path_or_id
    else:
        workspace_id = str(path_or_id)

    rows = list(workspaces.rows_where("workspace_id = ?", [workspace_id]))
    if not rows:
        return {"error": f"Workspace not found: {workspace_id}"}

    return _ws_to_dict(rows[0])


def list_workspaces(status: str = None, campaign_id: int = None) -> list:
    """List workspaces, optionally filtered.

    Args:
        status: Optional status filter (active, complete, blocked)
        campaign_id: Optional campaign filter

    Returns:
        List of workspace dicts
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    if status and campaign_id:
        rows = list(workspaces.rows_where(
            "status = ? AND campaign_id = ?",
            [status, campaign_id]
        ))
    elif status:
        rows = list(workspaces.rows_where("status = ?", [status]))
    elif campaign_id:
        rows = list(workspaces.rows_where("campaign_id = ?", [campaign_id]))
    else:
        rows = list(workspaces.rows)

    # Sort by created_at descending
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return [_ws_to_dict(r) for r in rows]


def get_sibling_failures(campaign_id: int) -> list:
    """Get failures from blocked workspaces in same campaign.

    Args:
        campaign_id: Campaign ID to search

    Returns:
        List of failure dicts from blocked siblings
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    blocked = list(workspaces.rows_where(
        "campaign_id = ? AND status = ?",
        [campaign_id, "blocked"]
    ))

    failures = []
    for ws in blocked:
        delivered = ws.get("delivered", "")
        ws_id = ws.get("workspace_id", "unknown")

        # Extract reason - handle multiple formats for robustness
        if delivered:
            if "BLOCKED:" in delivered:
                # Standard format from block() function
                reason = delivered.split("BLOCKED:", 1)[1].strip()
            elif "BLOCKED" in delivered.upper():
                # Case-insensitive variant
                idx = delivered.upper().find("BLOCKED")
                reason = delivered[idx + 7:].lstrip(":").strip()
            else:
                # No prefix - use delivered text directly
                reason = delivered.strip()
        else:
            # No delivered text - use generic message
            reason = f"Workspace {ws_id} blocked (no details)"

        # Extract first line as trigger, fallback to full reason if empty
        trigger = reason.split('\n')[0].strip() if reason else reason
        if not trigger:
            trigger = f"Blocked: {ws_id}"

        failures.append({
            "name": f"sibling-{ws_id}",
            "trigger": trigger,
            "fix": "See blocked workspace for attempted fixes",
            "cost": 1000,
            "source": [ws_id],
        })

    return failures


def clear_stale_workspaces(keep_campaign_id: int = None) -> dict:
    """Clear workspaces from completed campaigns.

    Args:
        keep_campaign_id: Optional campaign ID to preserve. If None, keeps
                          workspaces from active campaign only.

    Returns:
        {"cleared": count, "kept": count}
    """
    db = _ensure_db()
    workspaces = db.t.workspace
    campaigns = db.t.campaign

    # Determine which campaign(s) to keep
    if keep_campaign_id:
        keep_ids = {keep_campaign_id}
    else:
        # Keep only active campaign workspaces
        active_rows = list(campaigns.rows_where("status = ?", ["active"]))
        keep_ids = {r["id"] for r in active_rows}

    # Find and delete workspaces from other campaigns
    all_ws = list(workspaces.rows)
    cleared = 0
    kept = 0

    with db_write_lock:
        for ws in all_ws:
            if ws.get("campaign_id") in keep_ids:
                kept += 1
            else:
                workspaces.delete(ws["id"])
                cleared += 1

    return {"cleared": cleared, "kept": kept}


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_workspace_id(path: Path) -> str:
    """Extract workspace_id from virtual path.

    Args:
        path: Path in format {seq}_{slug}_{status}.xml

    Returns:
        workspace_id in format {seq}-{slug}

    Examples:
        '001_slug_active.xml' -> '001-slug'
        '001_add-power-tests_active.xml' -> '001-add-power-tests'
        '/path/to/002_foo-bar_complete.xml' -> '002-foo-bar'
    """
    stem = path.stem
    # Split from right to isolate status suffix
    parts = stem.rsplit("_", 1)
    if len(parts) == 2:
        name_part = parts[0]
        # Split from left on first underscore to get seq and slug
        name_parts = name_part.split("_", 1)
        if len(name_parts) == 2:
            return f"{name_parts[0]}-{name_parts[1]}"
    return stem


def _build_lineage(depends, campaign_id: int) -> dict:
    """Build lineage dict from parent workspaces."""
    if not depends or depends == "none":
        return {}

    if isinstance(depends, str):
        depends = [depends]

    db = _ensure_db()
    workspaces = db.t.workspace

    lineage = {"parents": []}
    for seq in depends:
        if not seq or seq == "none":
            continue

        # Find complete workspace for this seq in same campaign
        rows = list(workspaces.rows_where(
            "campaign_id = ? AND seq = ? AND status = ?",
            [campaign_id, seq, "complete"]
        ))

        if rows:
            parent = rows[0]
            lineage["parents"].append({
                "seq": seq,
                "workspace_id": parent["workspace_id"],
                "delivered": parent.get("delivered", "")
            })

    # Backwards compatibility: expose first parent
    if lineage["parents"]:
        first = lineage["parents"][0]
        lineage["parent"] = first["workspace_id"]
        lineage["prior_delivery"] = first["delivered"]

    return lineage


def _ws_to_dict(row) -> dict:
    """Convert workspace row to dict format."""
    # Helper for safe JSON parsing
    def safe_json_loads(data, default):
        """Parse JSON with fallback to default on error."""
        try:
            return json.loads(data) if data else default
        except (json.JSONDecodeError, TypeError):
            return default

    result = {
        "id": row["workspace_id"],
        "workspace_id": row["workspace_id"],
        "status": row["status"],
        "created_at": row.get("created_at"),
        "completed_at": row.get("completed_at"),
        "blocked_at": row.get("blocked_at"),
        "objective": row.get("objective", ""),
        "delta": safe_json_loads(row.get("delta"), []),
        "verify": row.get("verify", ""),
        "verify_source": row.get("verify_source"),
        "budget": row.get("budget", 5),
        "delivered": row.get("delivered", ""),
        "framework": row.get("framework"),
        "framework_confidence": row.get("framework_confidence", 1.0),
    }

    # Parse remaining JSON fields
    idioms = safe_json_loads(row.get("idioms"), {})
    if idioms:
        result["idioms"] = idioms

    prior_knowledge = safe_json_loads(row.get("prior_knowledge"), {})
    if prior_knowledge:
        result["prior_knowledge"] = prior_knowledge

    lineage = safe_json_loads(row.get("lineage"), {})
    if lineage:
        result["lineage"] = lineage

    utilized_memories = safe_json_loads(row.get("utilized_memories"), [])
    if utilized_memories:
        result["utilized_memories"] = utilized_memories

    code_contexts = safe_json_loads(row.get("code_contexts"), [])
    if code_contexts:
        result["code_contexts"] = code_contexts
        # Also set code_context for backwards compatibility
        if len(code_contexts) > 0:
            result["code_context"] = code_contexts[0]

    preflight = safe_json_loads(row.get("preflight"), [])
    if preflight:
        result["preflight"] = preflight

    return result


def _get_framework_confidence() -> float:
    """Get framework confidence from exploration."""
    import logging

    db = _ensure_db()
    explorations = db.t.exploration

    try:
        rows = list(explorations.rows)
        if rows:
            rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            pattern = json.loads(rows[0].get("pattern") or "{}")
            return float(pattern.get("confidence", 0.5))  # Default 0.5 for consistency
    except Exception as e:
        logging.warning(f"Failed to get framework confidence: {e}. Using default 0.5")

    return 0.5  # Changed from 1.0 for consistency (P4-14)


def _is_numeric_line_range(target_lines: str) -> bool:
    """Check if target_lines is a valid numeric range."""
    if not target_lines or "-" not in target_lines:
        return False
    parts = target_lines.split("-")
    if len(parts) != 2:
        return False
    try:
        start = int(parts[0].strip())
        end = int(parts[1].strip())
        return start > 0 and end > start
    except ValueError:
        return False


def extract_verify_source(verify_cmd: str) -> str | None:
    """Extract test file path from verify command."""
    import re

    if not verify_cmd:
        return None

    if "*" in verify_cmd:
        return None

    # Match quoted paths
    quoted_pattern = r'["\']([^"\']+\.py)["\']'
    quoted_match = re.search(quoted_pattern, verify_cmd)
    if quoted_match:
        path = quoted_match.group(1)
        if "test" in path.lower() or path.startswith("tests/"):
            return path

    # Match unquoted paths
    unquoted_pattern = r'(?:^|\s)((?:tests?/)?[\w/.-]+\.py)(?:\s|$)'
    for match in re.finditer(unquoted_pattern, verify_cmd):
        path = match.group(1)
        if "test" in path.lower() or path.startswith("tests/"):
            return path

    return None


def extract_code_context(
    file_path: Path,
    max_lines: int = 60,
    target_lines: str = None,
    task_type: str = "BUILD"
) -> dict | None:
    """Extract code context from a file."""
    if not file_path.exists():
        return None

    all_content = file_path.read_text()
    all_lines = all_content.split('\n')
    total_lines = len(all_lines)

    if task_type == "SPEC" or target_lines is None or not _is_numeric_line_range(target_lines):
        lines = all_lines[:max_lines]
        line_range = f"1-{min(len(lines), max_lines)}"
    else:
        lines = []
        ranges = []

        # Include imports
        import_end = min(15, total_lines)
        lines.extend(all_lines[:import_end])
        ranges.append(f"1-{import_end}")

        if _is_numeric_line_range(target_lines):
            parts = target_lines.split("-")
            start, end = int(parts[0].strip()), int(parts[1].strip())
            target_start = max(import_end, start - 5)
            target_end = min(total_lines, end + 10)

            if target_start > import_end:
                lines.append(f"# ... lines {import_end + 1}-{target_start - 1} omitted ...")
            lines.extend(all_lines[target_start:target_end])
            ranges.append(f"{target_start + 1}-{target_end}")

        line_range = ",".join(ranges)

    # Extract imports
    imports = []
    for line in all_lines[:30]:
        if line.startswith('import ') or line.startswith('from '):
            imports.append(line.strip())

    # Extract exports
    exports = []
    for line in lines:
        if line.startswith('def '):
            name = line.split('(')[0].replace('def ', '').strip()
            exports.append(f"{name}()")
        elif line.startswith('class '):
            name = line.split('(')[0].split(':')[0].replace('class ', '').strip()
            exports.append(name)
        elif '=' in line and not line.startswith(' ') and not line.startswith('#'):
            name = line.split('=')[0].strip()
            if name.isidentifier():
                exports.append(name)

    return {
        "path": str(file_path),
        "lines": line_range,
        "content": '\n'.join(lines),
        "exports": ', '.join(exports),
        "imports": '\n'.join(imports),
    }


def validate_workspace(workspace: dict, check_delta_exists: bool = True) -> tuple:
    """Validate a workspace has required fields.

    Args:
        workspace: Workspace dict to validate
        check_delta_exists: If True, verify delta files exist on filesystem

    Returns:
        (is_valid, issues) where issues is a list of validation problems
    """
    issues = []

    # Required fields check
    required = ["id", "status", "delta", "verify"]
    for field in required:
        if field not in workspace or workspace[field] is None:
            issues.append(f"missing:{field}")
        elif field == "delta" and not workspace[field]:
            issues.append("empty:delta")

    # Delta file existence check
    if check_delta_exists and "delta" in workspace and workspace["delta"]:
        delta_files = workspace["delta"]
        if isinstance(delta_files, str):
            delta_files = [delta_files]
        missing_files = []
        for f in delta_files:
            if not Path(f).exists():
                missing_files.append(f)
        if missing_files:
            issues.append(f"delta_not_found:{','.join(missing_files)}")

    return len(issues) == 0, issues


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL workspace operations")
    subparsers = parser.add_subparsers(dest="command")

    # create command
    c = subparsers.add_parser("create", help="Create workspaces from plan")
    c.add_argument("--plan-id", type=int, required=True, help="Plan ID from database")
    c.add_argument("--task", help="Specific task seq to create")

    # complete command
    comp = subparsers.add_parser("complete", help="Mark workspace complete")
    comp.add_argument("path", help="Path to workspace or workspace_id")
    comp.add_argument("--delivered", required=True, help="Delivery summary")
    comp.add_argument("--utilized", help="JSON array of utilized memories [{name, type}]")

    # block command
    b = subparsers.add_parser("block", help="Mark workspace blocked")
    b.add_argument("path", help="Path to workspace or workspace_id")
    b.add_argument("--reason", required=True, help="Block reason")

    # parse command
    p = subparsers.add_parser("parse", help="Parse workspace to JSON")
    p.add_argument("path", help="Path to workspace or workspace_id")

    # list command
    lst = subparsers.add_parser("list", help="List workspaces")
    lst.add_argument("--status", help="Filter by status")

    # get-injected command
    gi = subparsers.add_parser("get-injected", help="Get injected memories for a workspace")
    gi.add_argument("workspace", help="Workspace ID or path")

    # clear-stale command
    cs = subparsers.add_parser("clear-stale", help="Clear workspaces from completed campaigns")
    cs.add_argument("--keep", type=int, help="Campaign ID to preserve (default: active only)")

    args = parser.parse_args()

    if args.command == "create":
        plan = read_plan(args.plan_id)
        if not plan:
            print(json.dumps({"error": f"Plan {args.plan_id} not found"}))
            sys.exit(1)
        workspaces = create(plan, args.task)
        print(json.dumps({"created": workspaces}))

    elif args.command == "complete":
        utilized = json.loads(args.utilized) if args.utilized else None
        result = complete(args.path, args.delivered, utilized)
        print(json.dumps(result))

    elif args.command == "block":
        result = block(args.path, args.reason)
        print(json.dumps(result))

    elif args.command == "parse":
        result = parse(args.path)
        print(json.dumps(result, indent=2))

    elif args.command == "list":
        result = list_workspaces(status=args.status)
        print(json.dumps(result, indent=2))

    elif args.command == "get-injected":
        injected = []
        seen = set()  # Deduplicate across multiple workspaces

        # Check if workspace arg contains glob pattern
        if "*" in args.workspace:
            # Extract prefix before glob (e.g., "1-" from "1-*")
            prefix = args.workspace.replace("*", "")
            all_ws = list_workspaces()
            matching = [w for w in all_ws if w.get("workspace_id", "").startswith(prefix)]
            workspace_ids = [w["workspace_id"] for w in matching]
        else:
            workspace_ids = [args.workspace]

        for ws_id in workspace_ids:
            ws = parse(ws_id)
            if "error" in ws:
                continue
            prior = ws.get("prior_knowledge", {})
            for f in prior.get("failures", []):
                key = (f.get("name"), "failure")
                if key not in seen:
                    seen.add(key)
                    injected.append({"name": f.get("name"), "type": "failure"})
            for p in prior.get("patterns", []):
                key = (p.get("name"), "pattern")
                if key not in seen:
                    seen.add(key)
                    injected.append({"name": p.get("name"), "type": "pattern"})
            for sf in prior.get("sibling_failures", []):
                key = (sf.get("name"), "failure")
                if key not in seen:
                    seen.add(key)
                    injected.append({"name": sf.get("name"), "type": "failure"})
        print(json.dumps(injected))

    elif args.command == "clear-stale":
        result = clear_stale_workspaces(keep_campaign_id=args.keep)
        print(json.dumps(result))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
