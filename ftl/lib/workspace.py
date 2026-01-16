#!/usr/bin/env python3
"""Workspace operations with clear contracts."""

from pathlib import Path
from datetime import datetime
import json
import argparse
import sys
import xml.etree.ElementTree as ET

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


WORKSPACE_DIR = Path(".ftl/workspace")


def extract_error_from_delivered(delivered: str) -> str:
    """Extract error message from BLOCKED: delivered text.

    Args:
        delivered: The delivered field containing "BLOCKED: ..." text

    Returns:
        The first line of the error/reason
    """
    if "BLOCKED:" in delivered:
        reason = delivered.split("BLOCKED:", 1)[1].strip()
        # Take first line as trigger
        return reason.split('\n')[0].strip()
    return delivered[:100]


def get_sibling_failures(workspace_dir: Path) -> list[dict]:
    """Get failures from blocked sibling workspaces for intra-campaign learning.

    Args:
        workspace_dir: Path to workspace directory

    Returns:
        List of failure dicts from blocked siblings
    """
    failures = []
    if not workspace_dir.exists():
        return failures

    for blocked_path in workspace_dir.glob("*_blocked.xml"):
        try:
            blocked_data = parse(blocked_path)
            delivered = blocked_data.get("delivered", "")
            if delivered and "BLOCKED:" in delivered:
                failures.append({
                    "name": f"sibling-{blocked_path.stem}",
                    "trigger": extract_error_from_delivered(delivered),
                    "fix": "See blocked workspace for attempted fixes",
                    "cost": 1000,  # Default cost for sibling failures
                    "source": [blocked_path.stem],
                })
        except Exception:
            pass  # Skip malformed workspaces

    return failures


def extract_code_context(
    file_path: Path,
    max_lines: int = 60,
    target_lines: str = None,
    task_type: str = "BUILD"
) -> dict | None:
    """Extract code context from a file.

    Args:
        file_path: Path to the file
        max_lines: Default max lines for SPEC tasks
        target_lines: Optional line range hint (e.g., "45-80") for BUILD tasks
        task_type: SPEC or BUILD - affects context strategy

    Returns:
        {path, lines, content, exports, imports} or None if file doesn't exist
    """
    if not file_path.exists():
        return None

    all_content = file_path.read_text()
    all_lines = all_content.split('\n')
    total_lines = len(all_lines)

    # Strategy: SPEC tasks get beginning, BUILD tasks get strategic context
    if task_type == "SPEC" or target_lines is None:
        # SPEC: Just grab the first N lines (tests usually at end anyway)
        lines = all_lines[:max_lines]
        line_range = f"1-{min(len(lines), max_lines)}"
    else:
        # BUILD: Strategic context including imports + target function area
        lines = []
        ranges = []

        # Always include imports (first 15 lines typically)
        import_end = min(15, total_lines)
        lines.extend(all_lines[:import_end])
        ranges.append(f"1-{import_end}")

        # Parse target_lines (e.g., "45-80" or "100-150")
        if "-" in target_lines:
            start, end = map(int, target_lines.split("-"))
            # Add buffer around target (5 lines before, 10 after)
            target_start = max(import_end, start - 5)
            target_end = min(total_lines, end + 10)

            if target_start > import_end:
                lines.append(f"# ... lines {import_end + 1}-{target_start - 1} omitted ...")
            lines.extend(all_lines[target_start:target_end])
            ranges.append(f"{target_start + 1}-{target_end}")

        line_range = ",".join(ranges)

    # Extract imports (Python)
    imports = []
    for line in all_lines[:30]:  # Always scan first 30 for imports
        if line.startswith('import ') or line.startswith('from '):
            imports.append(line.strip())

    # Extract exports (functions, classes, variables at module level)
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


def create(plan: dict, task_seq: str = None) -> list:
    """Create workspace XML files from plan.

    Args:
        plan: Plan dict with campaign, framework, idioms, tasks
        task_seq: Optional specific task seq to create

    Returns:
        List of created Path objects
    """
    from memory import get_context

    paths = []
    tasks = plan.get("tasks", [])

    if task_seq:
        tasks = [t for t in tasks if t["seq"] == task_seq]

    for task in tasks:
        ws_id = f"{task['seq']}-{task['slug']}"
        filename = f"{task['seq']}_{task['slug']}_active.xml"
        path = WORKSPACE_DIR / filename

        root = ET.Element("workspace", id=ws_id, status="active")
        root.set("created_at", datetime.now().isoformat())

        # Objective (from plan, so builder knows the WHY not just the WHAT)
        objective = plan.get("objective", "")
        if objective:
            ET.SubElement(root, "objective").text = objective

        # Implementation
        impl = ET.SubElement(root, "implementation")
        for delta in task.get("delta", []):
            ET.SubElement(impl, "delta").text = delta
        ET.SubElement(impl, "verify").text = task.get("verify", "")

        # verify_source: test file that builder should read BEFORE implementing
        # Either explicit from planner, or derived from verify command
        verify_source = task.get("verify_source")
        if not verify_source:
            # Try to extract test file from verify command (e.g., "pytest tests/test_foo.py")
            verify_cmd = task.get("verify", "")
            if "pytest" in verify_cmd or "test" in verify_cmd:
                for word in verify_cmd.split():
                    if word.endswith(".py") and ("test" in word.lower() or word.startswith("tests/")):
                        verify_source = word
                        break
        if verify_source:
            ET.SubElement(impl, "verify_source").text = verify_source
        ET.SubElement(impl, "budget").text = str(task.get("budget", 5))

        # Preflight checks
        for pf in task.get("preflight", []):
            ET.SubElement(impl, "preflight").text = pf

        # Code context for ALL delta files (not just first)
        # Use target_lines from plan if available (set by planner for BUILD tasks)
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
                    code_ctx = ET.SubElement(
                        root, "code_context",
                        path=ctx["path"],
                        lines=ctx["lines"]
                    )
                    content_elem = ET.SubElement(code_ctx, "content")
                    content_elem.text = ctx["content"]
                    ET.SubElement(code_ctx, "exports").text = ctx["exports"]
                    ET.SubElement(code_ctx, "imports").text = ctx["imports"]
                # No break - process ALL delta files

        # Framework idioms
        framework = plan.get("framework")
        if framework and framework != "none":
            idioms_elem = ET.SubElement(root, "idioms", framework=framework)
            for req in plan.get("idioms", {}).get("required", []):
                ET.SubElement(idioms_elem, "required").text = req
            for forb in plan.get("idioms", {}).get("forbidden", []):
                ET.SubElement(idioms_elem, "forbidden").text = forb

        # Prior knowledge from memory + blocked siblings (intra-campaign learning)
        memory_failures = []
        memory_patterns = []

        try:
            tags = [framework.lower()] if framework and framework != "none" else None

            # Build semantic context from campaign objective, task slug, and delta files
            # This enables semantic retrieval of relevant memories
            task_context = " ".join(filter(None, [
                plan.get("objective", ""),
                task.get("slug", "").replace("-", " "),
                " ".join(task.get("delta", [])),
            ]))

            memory_ctx = get_context(
                task_type=task.get("type", "BUILD"),
                tags=tags,
                objective=task_context if task_context.strip() else None,
                max_failures=5,
                max_patterns=3
            )
            memory_failures = memory_ctx.get("failures", [])
            memory_patterns = memory_ctx.get("patterns", [])
        except ImportError:
            pass  # Memory not available

        # Add failures from blocked siblings (intra-campaign learning)
        sibling_failures = get_sibling_failures(WORKSPACE_DIR)

        all_failures = memory_failures + sibling_failures
        all_patterns = memory_patterns

        if all_failures or all_patterns:
            pk = ET.SubElement(root, "prior_knowledge")

            for f in all_failures:
                # Mark memory-sourced entries as injected for feedback tracking
                is_sibling = f.get("name", "").startswith("sibling-")
                failure = ET.SubElement(
                    pk, "failure",
                    name=f.get("name", ""),
                    cost=str(f.get("cost", 0)),
                    injected="true" if not is_sibling else "false"
                )
                ET.SubElement(failure, "trigger").text = f.get("trigger", "")
                ET.SubElement(failure, "fix").text = f.get("fix", "")
                if f.get("match"):
                    ET.SubElement(failure, "match").text = f["match"]

            for p in all_patterns:
                pattern = ET.SubElement(
                    pk, "pattern",
                    name=p.get("name", ""),
                    saved=str(p.get("saved", 0)),
                    injected="true"
                )
                ET.SubElement(pattern, "trigger").text = p.get("trigger", "")
                ET.SubElement(pattern, "insight").text = p.get("insight", "")

        # Lineage (from depends) - supports both single string and array of dependencies
        depends = task.get("depends")
        if depends and depends != "none":
            # Normalize to list for DAG support
            if isinstance(depends, str):
                depends_list = [depends]
            else:
                depends_list = [d for d in depends if d and d != "none"]

            if depends_list:
                lineage = ET.SubElement(root, "lineage")
                for dep in depends_list:
                    parent_ws = list(WORKSPACE_DIR.glob(f"{dep}_*_complete.xml"))
                    if parent_ws:
                        parent_data = parse(parent_ws[0])
                        parent_elem = ET.SubElement(lineage, "parent", seq=dep)
                        parent_elem.set("workspace", parent_ws[0].stem)
                        delivered = parent_data.get("delivered", "")
                        ET.SubElement(parent_elem, "prior_delivery").text = delivered

        # Delivered (empty initially)
        ET.SubElement(root, "delivered")

        # Write
        path.parent.mkdir(parents=True, exist_ok=True)
        tree = ET.ElementTree(root)
        tree.write(path, encoding="unicode", xml_declaration=True)
        paths.append(path)

    return paths


def complete(path: Path, delivered: str, utilized_memories: list = None) -> Path:
    """Mark workspace complete.

    Args:
        path: Path to active workspace XML
        delivered: Summary of what was delivered
        utilized_memories: List of {"name": str, "type": "failure"|"pattern"} that were helpful

    Returns:
        New path (with _complete suffix)
    """
    tree = ET.parse(path)
    root = tree.getroot()

    root.set("status", "complete")
    root.set("completed_at", datetime.now().isoformat())

    delivered_elem = root.find("delivered")
    if delivered_elem is None:
        delivered_elem = ET.SubElement(root, "delivered")
    delivered_elem.text = delivered

    # Track utilized memories for feedback loop
    if utilized_memories:
        utilization = ET.SubElement(root, "memory_utilization")
        for mem in utilized_memories:
            ET.SubElement(
                utilization, "utilized",
                name=mem.get("name", ""),
                type=mem.get("type", "failure")
            )

    new_path = path.parent / path.name.replace("_active.xml", "_complete.xml")
    tree.write(new_path, encoding="unicode", xml_declaration=True)
    path.unlink()

    return new_path


def block(path: Path, reason: str) -> Path:
    """Mark workspace blocked.

    Args:
        path: Path to active workspace XML
        reason: Why it was blocked

    Returns:
        New path (with _blocked suffix)
    """
    tree = ET.parse(path)
    root = tree.getroot()

    root.set("status", "blocked")
    root.set("blocked_at", datetime.now().isoformat())

    delivered_elem = root.find("delivered")
    if delivered_elem is None:
        delivered_elem = ET.SubElement(root, "delivered")
    delivered_elem.text = f"BLOCKED: {reason}"

    new_path = path.parent / path.name.replace("_active.xml", "_blocked.xml")
    tree.write(new_path, encoding="unicode", xml_declaration=True)
    path.unlink()

    return new_path


def parse(path: Path) -> dict:
    """Parse workspace XML to dict."""
    tree = ET.parse(path)
    root = tree.getroot()

    result = {
        "id": root.get("id"),
        "status": root.get("status"),
        "created_at": root.get("created_at"),
        "completed_at": root.get("completed_at"),
        "blocked_at": root.get("blocked_at"),
        "objective": root.findtext("objective", ""),
        "delta": [d.text for d in root.findall(".//implementation/delta")],
        "verify": root.findtext(".//implementation/verify", ""),
        "verify_source": root.findtext(".//implementation/verify_source", ""),
        "budget": int(root.findtext(".//implementation/budget", "5")),
        "preflight": [p.text for p in root.findall(".//implementation/preflight")],
        "delivered": root.findtext("delivered", ""),
    }

    # Code context(s) - now supports multiple for multi-file delta
    code_contexts = root.findall("code_context")
    if code_contexts:
        if len(code_contexts) == 1:
            # Single context (backwards compatible)
            code_ctx = code_contexts[0]
            result["code_context"] = {
                "path": code_ctx.get("path"),
                "lines": code_ctx.get("lines"),
                "content": code_ctx.findtext("content", ""),
                "exports": code_ctx.findtext("exports", ""),
                "imports": code_ctx.findtext("imports", ""),
            }
        else:
            # Multiple contexts
            result["code_contexts"] = [
                {
                    "path": ctx.get("path"),
                    "lines": ctx.get("lines"),
                    "content": ctx.findtext("content", ""),
                    "exports": ctx.findtext("exports", ""),
                    "imports": ctx.findtext("imports", ""),
                }
                for ctx in code_contexts
            ]
            # Also keep first as code_context for backwards compatibility
            result["code_context"] = result["code_contexts"][0]

    # Idioms
    idioms = root.find("idioms")
    if idioms is not None:
        result["framework"] = idioms.get("framework")
        result["idioms"] = {
            "required": [r.text for r in idioms.findall("required")],
            "forbidden": [f.text for f in idioms.findall("forbidden")],
        }

    # Prior knowledge
    pk = root.find("prior_knowledge")
    if pk is not None:
        result["prior_knowledge"] = {
            "failures": [
                {
                    "name": f.get("name"),
                    "cost": int(f.get("cost", 0)),
                    "trigger": f.findtext("trigger", ""),
                    "fix": f.findtext("fix", ""),
                    "match": f.findtext("match"),
                    "injected": f.get("injected") == "true",
                }
                for f in pk.findall("failure")
            ],
            "patterns": [
                {
                    "name": p.get("name"),
                    "saved": int(p.get("saved", 0)),
                    "trigger": p.findtext("trigger", ""),
                    "insight": p.findtext("insight", ""),
                    "injected": p.get("injected") == "true",
                }
                for p in pk.findall("pattern")
            ],
        }

    # Memory utilization (for feedback loop)
    utilization = root.find("memory_utilization")
    if utilization is not None:
        result["utilized_memories"] = [
            {
                "name": u.get("name"),
                "type": u.get("type", "failure"),
            }
            for u in utilization.findall("utilized")
        ]

    # Lineage - supports multiple parents (DAG dependencies)
    lineage = root.find("lineage")
    if lineage is not None:
        parents = lineage.findall("parent")
        if parents and parents[0].get("seq"):
            # New multi-parent format: <parent seq="001" workspace="..."><prior_delivery>...</prior_delivery></parent>
            result["lineage"] = {
                "parents": [
                    {
                        "seq": p.get("seq"),
                        "workspace": p.get("workspace"),
                        "prior_delivery": p.findtext("prior_delivery", ""),
                    }
                    for p in parents
                ],
            }
            # Backwards compatibility: expose first parent in old format
            if result["lineage"]["parents"]:
                first = result["lineage"]["parents"][0]
                result["lineage"]["parent"] = first["workspace"]
                result["lineage"]["prior_delivery"] = first["prior_delivery"]
        else:
            # Legacy single-parent format: <parent>...</parent><prior_delivery>...</prior_delivery>
            result["lineage"] = {
                "parent": lineage.findtext("parent", ""),
                "prior_delivery": lineage.findtext("prior_delivery", ""),
                "parents": [{
                    "seq": None,
                    "workspace": lineage.findtext("parent", ""),
                    "prior_delivery": lineage.findtext("prior_delivery", ""),
                }],
            }

    return result


def main():
    parser = argparse.ArgumentParser(description="FTL workspace operations")
    subparsers = parser.add_subparsers(dest="command")

    # create command
    c = subparsers.add_parser("create", help="Create workspaces from plan")
    c.add_argument("--plan", required=True, help="Path to plan.json or - for stdin")
    c.add_argument("--task", help="Specific task seq to create")

    # complete command
    comp = subparsers.add_parser("complete", help="Mark workspace complete")
    comp.add_argument("path", help="Path to active workspace XML")
    comp.add_argument("--delivered", required=True, help="Delivery summary")
    comp.add_argument("--utilized", help="JSON array of utilized memories [{name, type}]")

    # block command
    b = subparsers.add_parser("block", help="Mark workspace blocked")
    b.add_argument("path", help="Path to active workspace XML")
    b.add_argument("--reason", required=True, help="Block reason")

    # parse command
    p = subparsers.add_parser("parse", help="Parse workspace to JSON")
    p.add_argument("path", help="Path to workspace XML")

    args = parser.parse_args()

    if args.command == "create":
        if args.plan == "-":
            plan = json.load(sys.stdin)
        else:
            plan = json.loads(Path(args.plan).read_text())
        paths = create(plan, args.task)
        for p in paths:
            print(f"Created: {p}")

    elif args.command == "complete":
        utilized = json.loads(args.utilized) if args.utilized else None
        new_path = complete(Path(args.path), args.delivered, utilized)
        print(f"Completed: {new_path}")

    elif args.command == "block":
        new_path = block(Path(args.path), args.reason)
        print(f"Blocked: {new_path}")

    elif args.command == "parse":
        result = parse(Path(args.path))
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
