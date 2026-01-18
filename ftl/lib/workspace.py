#!/usr/bin/env python3
"""Workspace operations with fastsql database backend.

Provides workspace lifecycle management, code context extraction,
and memory injection for builder agents.

CRITICAL API PRESERVATION:
- create(plan, task_seq) -> list[Path]
- complete(path: Path, delivered, utilized) -> Path
- block(path: Path, reason) -> Path
Path parameters preserved for signature compatibility.
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
    from lib.db import get_db, init_db, Workspace
    from lib.framework_registry import get_idioms
    from lib.plan import read as read_plan
except ImportError:
    from db import get_db, init_db, Workspace
    from framework_registry import get_idioms
    from plan import read as read_plan


# Virtual path prefix (for API compatibility, no files created)
WORKSPACE_DIR = Path(".ftl/workspace")


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

    PRESERVES EXISTING API: Returns list[Path] for compatibility.

    Args:
        plan: Plan dict with tasks[]
        task_seq: Optional specific task seq to create

    Returns:
        List of Path objects (virtual paths for compatibility)
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
    except (ImportError, Exception):
        pass

    # Get sibling failures from blocked workspaces
    sibling_failures = get_sibling_failures(campaign["id"])
    memory_ctx["sibling_failures"] = sibling_failures

    paths = []
    tasks = plan.get("tasks", [])

    if task_seq:
        tasks = [t for t in tasks if t["seq"] == task_seq]

    for task in tasks:
        ws_id = f"{task['seq']}-{task['slug']}"

        # Check if workspace already exists
        existing = list(workspaces.rows_where("workspace_id = ?", [ws_id]))
        if existing:
            # Return existing path
            ws = existing[0]
            path = WORKSPACE_DIR / f"{task['seq']}_{task['slug']}_{ws['status']}.xml"
            paths.append(path)
            continue

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

        workspaces.insert(ws)

        # Return Path for compatibility
        path = WORKSPACE_DIR / f"{task['seq']}_{task['slug']}_active.xml"
        paths.append(path)

    return paths


def complete(path: Path, delivered: str, utilized_memories: list = None) -> Path:
    """Mark workspace complete.

    PRESERVES EXISTING API: Takes Path, returns Path.

    Args:
        path: Path to workspace (used to extract workspace_id)
        delivered: Summary of what was delivered
        utilized_memories: List of {"name": str, "type": str} that were helpful

    Returns:
        New path with _complete suffix
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    workspace_id = _extract_workspace_id(path)
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

    # Return new path with _complete suffix
    new_path = path.parent / path.name.replace("_active.xml", "_complete.xml")
    return new_path


def block(path: Path, reason: str) -> Path:
    """Mark workspace blocked.

    PRESERVES EXISTING API: Takes Path, returns Path.

    Args:
        path: Path to workspace (used to extract workspace_id)
        reason: Why it was blocked

    Returns:
        New path with _blocked suffix
    """
    db = _ensure_db()
    workspaces = db.t.workspace

    workspace_id = _extract_workspace_id(path)
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

    # Return new path with _blocked suffix
    new_path = path.parent / path.name.replace("_active.xml", "_blocked.xml")
    return new_path


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
        if delivered and "BLOCKED:" in delivered:
            reason = delivered.split("BLOCKED:", 1)[1].strip()
            failures.append({
                "name": f"sibling-{ws['workspace_id']}",
                "trigger": reason.split('\n')[0].strip(),
                "fix": "See blocked workspace for attempted fixes",
                "cost": 1000,
                "source": [ws["workspace_id"]],
            })

    return failures


# =============================================================================
# Helper Functions
# =============================================================================

def _extract_workspace_id(path: Path) -> str:
    """Extract workspace_id from path.

    Examples:
        '001_slug_active.xml' -> '001-slug'
        '/path/to/002_foo_complete.xml' -> '002-foo'
    """
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
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
    db = _ensure_db()
    explorations = db.t.exploration

    try:
        rows = list(explorations.rows)
        if rows:
            rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
            pattern = json.loads(rows[0].get("pattern") or "{}")
            return float(pattern.get("confidence", 1.0))
    except Exception:
        pass

    return 1.0


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


def extract_error_from_delivered(delivered: str) -> str:
    """Extract error message from BLOCKED: delivered text."""
    if "BLOCKED:" in delivered:
        reason = delivered.split("BLOCKED:", 1)[1].strip()
        return reason.split('\n')[0].strip()
    return delivered[:100]


def validate_workspace(workspace: dict) -> tuple:
    """Validate a workspace has required fields."""
    required = ["id", "status", "delta", "verify"]
    missing = []
    for field in required:
        if field not in workspace or workspace[field] is None:
            missing.append(field)
        elif field == "delta" and not workspace[field]:
            missing.append(f"{field} (empty)")

    return len(missing) == 0, missing


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
    gi.add_argument("--workspace", required=True, help="Workspace ID or path")

    args = parser.parse_args()

    if args.command == "create":
        plan = read_plan(args.plan_id)
        if not plan:
            print(f"Error: Plan {args.plan_id} not found", file=sys.stderr)
            sys.exit(1)
        paths = create(plan, args.task)
        for p in paths:
            print(f"Created: {p}")

    elif args.command == "complete":
        utilized = json.loads(args.utilized) if args.utilized else None
        path = Path(args.path) if "/" in args.path or args.path.endswith(".xml") else Path(f".ftl/workspace/{args.path}_active.xml")
        new_path = complete(path, args.delivered, utilized)
        print(f"Completed: {new_path}")

    elif args.command == "block":
        path = Path(args.path) if "/" in args.path or args.path.endswith(".xml") else Path(f".ftl/workspace/{args.path}_active.xml")
        new_path = block(path, args.reason)
        print(f"Blocked: {new_path}")

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

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
