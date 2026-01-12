"""
FTL Memory - Unified memory system.

Version 4.0 - Single source of truth. Clean break.

Memory stores:
- failures: What broke and how to fix/prevent
- discoveries: Non-obvious approaches that saved tokens
- decisions: Workspace index with tags and metadata
- edges: Relationships (lineage, file_impact)
"""

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import date
from typing import Optional
from collections import defaultdict

try:
    from concepts import expand_query
except ImportError:
    def expand_query(term):
        return [term.lower()]

MEMORY_VERSION = "4.0"
# Strict pattern: requires .xml extension and specific status values
FILENAME_PATTERN = re.compile(r'^(\d{3})_(.+?)_(active|complete|blocked)(?:_from-(\d{3}))?\.xml$')

# Known frameworks for synthesizer gate
KNOWN_FRAMEWORKS = {
    'fasthtml', 'fastapi', 'flask', 'django', 'fastlite',
    'starlette', 'litestar', 'quart', 'sanic', 'tornado',
    'sqlalchemy', 'pydantic', 'pytest', 'numpy', 'pandas'
}
# Lenient pattern for internal use: matches stem without extension
FILENAME_PATTERN_STEM = re.compile(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$')


def parse_workspace_filename(filename: str) -> Optional[dict]:
    """Parse workspace filename into components.

    Single source of truth for workspace naming convention.
    Requires .xml extension and valid status (active|complete|blocked).

    Args:
        filename: Full filename with .xml extension (NNN_slug_status.xml)

    Returns:
        dict with seq, slug, status, parent (or None if no match)
    """
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None
    seq, slug, status, parent = match.groups()
    return {"seq": seq, "slug": slug, "status": status, "parent": parent}


def parse_workspace_stem(stem: str) -> Optional[dict]:
    """Parse workspace filename stem (without extension).

    More lenient - for internal use when dealing with Path.stem values.

    Args:
        stem: Filename without extension (NNN_slug_status)

    Returns:
        dict with seq, slug, status, parent (or None if no match)
    """
    match = FILENAME_PATTERN_STEM.match(stem)
    if not match:
        return None
    seq, slug, status, parent = match.groups()
    return {"seq": seq, "slug": slug, "status": status, "parent": parent}


def _empty_memory() -> dict:
    return {
        "version": MEMORY_VERSION,
        "updated": date.today().isoformat(),
        "failures": [],
        "discoveries": [],
        "decisions": {},
        "edges": {"lineage": {}, "file_impact": {}}
    }


def load_memory(path: Path) -> dict:
    """Load memory file, return empty if missing."""
    if not path.exists():
        return _empty_memory()
    return json.loads(path.read_text())


def save_memory(memory: dict, path: Path) -> None:
    """Write memory file."""
    memory["version"] = MEMORY_VERSION
    memory["updated"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, indent=2))


def add_failure(memory: dict, failure: dict) -> dict:
    """Add or merge a failure mode."""
    existing = next((f for f in memory.get("failures", []) if f["name"] == failure["name"]), None)
    if existing:
        existing["source"] = list(set(existing.get("source", []) + failure.get("source", [])))
        existing["cost"] = existing.get("cost", 0) + failure.get("cost", 0)
    else:
        if "failures" not in memory:
            memory["failures"] = []
        failure["id"] = f"f{len(memory['failures'])+1:03d}"
        failure["created"] = date.today().isoformat()
        failure.setdefault("tags", [])
        failure.setdefault("source", [])
        failure.setdefault("signal", 0)
        memory["failures"].append(failure)
    return memory


def add_discovery(memory: dict, discovery: dict) -> dict:
    """Add or merge a discovery."""
    existing = next((d for d in memory.get("discoveries", []) if d["name"] == discovery["name"]), None)
    if existing:
        existing["source"] = list(set(existing.get("source", []) + discovery.get("source", [])))
        existing["tokens_saved"] = existing.get("tokens_saved", 0) + discovery.get("tokens_saved", 0)
        if discovery.get("evidence") and discovery["evidence"] not in existing.get("evidence", ""):
            existing["evidence"] = existing.get("evidence", "") + "; " + discovery["evidence"]
    else:
        if "discoveries" not in memory:
            memory["discoveries"] = []
        discovery["id"] = f"d{len(memory['discoveries'])+1:03d}"
        discovery["created"] = date.today().isoformat()
        discovery.setdefault("tags", [])
        discovery.setdefault("source", [])
        discovery.setdefault("signal", 0)
        memory["discoveries"].append(discovery)
    return memory


def add_signal(memory: dict, entity_id: str, signal: str) -> dict:
    """Add +/- signal to a failure or discovery."""
    entity = None
    for f in memory.get("failures", []):
        if f.get("id") == entity_id:
            entity = f
            break
    if not entity:
        for d in memory.get("discoveries", []):
            if d.get("id") == entity_id:
                entity = d
                break
    if entity:
        current = entity.get("signal", 0)
        entity["signal"] = current + 1 if signal == "+" else current - 1
    return memory


def get_context_for_task(memory: dict, tags: Optional[list[str]] = None) -> dict:
    """Select relevant failures and discoveries."""
    def matches_tags(item):
        if not tags:
            return True
        return any(t in item.get("tags", []) for t in tags)

    return {
        "failures": sorted(
            [f for f in memory.get("failures", []) if matches_tags(f)],
            key=lambda f: -f.get("cost", 0)
        ),
        "discoveries": sorted(
            [d for d in memory.get("discoveries", []) if matches_tags(d)],
            key=lambda d: -d.get("tokens_saved", 0)
        )
    }


def format_for_injection(context: dict) -> str:
    """Format context as markdown for agent injection."""
    lines = []
    failures = context.get("failures", [])
    if failures:
        lines.append("## Known Failures\n")
        for f in failures:
            lines.append(f"- **{f['name']}** (cost: {f.get('cost', 0)//1000}k)")
            lines.append(f"  Trigger: {f.get('trigger', 'unknown')}")
            lines.append(f"  Fix: {f.get('fix', 'unknown')}")
            lines.append("")
        preflights = [f for f in failures if f.get("prevent")]
        if preflights:
            lines.append("## Pre-flight\n")
            for f in preflights:
                lines.append(f"- [ ] `{f['prevent']}`")
            lines.append("")
    discoveries = context.get("discoveries", [])
    if discoveries:
        lines.append("## Discoveries\n")
        for d in discoveries:
            lines.append(f"- **{d['name']}** (saved: {d.get('tokens_saved', 0)//1000}k)")
            lines.append(f"  When: {d.get('trigger', 'unknown')}")
            lines.append(f"  Insight: {d.get('insight', 'unknown')}")
            lines.append("")
    return "\n".join(lines)


def inject_and_log(memory: dict, run_id: str, tags: Optional[list[str]] = None, log_path: Optional[Path] = None) -> tuple[str, dict]:
    """Format injection and create tracking log."""
    context = get_context_for_task(memory, tags)
    markdown = format_for_injection(context)
    log = {
        "run_id": run_id,
        "timestamp": date.today().isoformat(),
        "failures": {"injected": [f["id"] for f in context.get("failures", [])]},
        "discoveries": {"injected": [d["id"] for d in context.get("discoveries", [])]}
    }
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(json.dumps(log, indent=2))
    return markdown, log


def parse_workspace_xml(path: Path) -> Optional[dict]:
    """Parse XML workspace file into decision record."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        return None
    parsed = parse_workspace_filename(path.name)
    if not parsed:
        return None
    seq, slug, status, parent = parsed["seq"], parsed["slug"], parsed["status"], parsed["parent"]
    delta_files = [d.text for d in root.findall('.//implementation/delta') if d.text]
    delivered_elem = root.find('.//delivered')
    delivered = delivered_elem.text if delivered_elem is not None and delivered_elem.text else ''
    tags = []
    for p in root.findall('.//pattern'):
        if p.get('name'):
            tags.append(f"#pattern/{p.get('name')}")
    for f in root.findall('.//failure'):
        if f.get('name'):
            tags.append(f"#failure/{f.get('name')}")
    return {
        "seq": seq, "slug": slug, "status": status, "parent": parent,
        "mtime": path.stat().st_mtime, "file": path.name,
        "delta_files": delta_files, "delivered": delivered[:500], "tags": tags
    }


def mine_workspace(workspace_dir: Path, memory_path: Path) -> dict:
    """Build decision index from workspace files."""
    memory = load_memory(memory_path)
    decisions = {}
    edges = {"lineage": {}, "file_impact": defaultdict(list)}
    for path in sorted(workspace_dir.glob("*.xml")):
        parsed = parse_workspace_xml(path)
        if not parsed:
            continue
        seq = parsed["seq"]
        decisions[seq] = {
            "file": parsed["file"], "slug": parsed["slug"], "mtime": parsed["mtime"],
            "status": parsed["status"], "parent": parsed["parent"],
            "delta_files": parsed["delta_files"], "delivered": parsed["delivered"], "tags": parsed["tags"]
        }
        if parsed["parent"]:
            edges["lineage"][seq] = parsed["parent"]
        for f in parsed["delta_files"]:
            if seq not in edges["file_impact"][f]:
                edges["file_impact"][f].append(seq)
    edges["file_impact"] = dict(edges["file_impact"])
    memory["decisions"] = decisions
    memory["edges"] = edges
    save_memory(memory, memory_path)
    return memory


def get_decision(seq: str, memory: dict) -> Optional[dict]:
    """Get decision by sequence number."""
    seq = seq.zfill(3)
    d = memory.get("decisions", {}).get(seq)
    if d:
        d = dict(d)
        d["seq"] = seq
    return d


def get_lineage(seq: str, memory: dict) -> list:
    """Get ancestry chain."""
    decisions = memory.get("decisions", {})
    lineage_map = memory.get("edges", {}).get("lineage", {})
    chain = []
    current = seq.zfill(3)
    while current and current in decisions:
        chain.append(current)
        current = lineage_map.get(current)
    chain.reverse()
    return chain


def query_decisions(topic: Optional[str], memory: dict) -> list:
    """Query decisions, optionally filtered by topic."""
    decisions = memory.get("decisions", {})
    if not topic:
        results = []
        for seq, d in decisions.items():
            results.append({
                "seq": seq, "slug": d.get("slug", ""), "status": d.get("status", ""),
                "parent": d.get("parent"), "age_days": int((time.time() - d.get("mtime", 0)) / 86400),
                "tags": d.get("tags", []), "file": d.get("file", "")
            })
        return sorted(results, key=lambda x: -decisions.get(x["seq"], {}).get("mtime", 0))
    expanded = expand_query(topic)
    results = []
    for seq, d in decisions.items():
        searchable = " ".join([d.get('slug', ''), d.get('delivered', ''), ' '.join(d.get('tags', [])), ' '.join(d.get('delta_files', []))]).lower()
        if any(t in searchable for t in expanded):
            results.append({
                "seq": seq, "slug": d.get("slug", ""), "status": d.get("status", ""),
                "parent": d.get("parent"), "age_days": int((time.time() - d.get("mtime", 0)) / 86400),
                "tags": d.get("tags", []), "file": d.get("file", "")
            })
    return sorted(results, key=lambda x: -decisions.get(x["seq"], {}).get("mtime", 0))


def trace_tag(tag: str, memory: dict) -> list:
    """Find decisions that used a tag."""
    decisions = memory.get("decisions", {})
    results = []
    for seq, d in decisions.items():
        if tag in d.get("tags", []):
            results.append({
                "seq": seq, "slug": d.get("slug", ""), "status": d.get("status", ""),
                "age_days": int((time.time() - d.get("mtime", 0)) / 86400), "file": d.get("file", "")
            })
    return sorted(results, key=lambda x: x["seq"])


def impact_file(file_pattern: str, memory: dict) -> list:
    """Find decisions that touched a file."""
    decisions = memory.get("decisions", {})
    file_impact = memory.get("edges", {}).get("file_impact", {})
    results = []
    seen = set()
    for pattern, seqs in file_impact.items():
        if file_pattern.lower() in pattern.lower():
            for seq in seqs:
                if seq not in seen and seq in decisions:
                    seen.add(seq)
                    d = decisions[seq]
                    results.append({
                        "seq": seq, "slug": d.get("slug", ""), "status": d.get("status", ""),
                        "age_days": int((time.time() - d.get("mtime", 0)) / 86400),
                        "file": d.get("file", ""), "delta_files": d.get("delta_files", [])
                    })
    return sorted(results, key=lambda x: x["seq"])


def find_stale(days: int, memory: dict) -> list:
    """Find decisions older than threshold."""
    threshold = time.time() - (days * 86400)
    decisions = memory.get("decisions", {})
    stale = []
    for seq, d in decisions.items():
        if d.get("mtime", 0) < threshold:
            stale.append({
                "seq": seq, "slug": d.get("slug", ""),
                "age_days": int((time.time() - d.get("mtime", 0)) / 86400),
                "file": d.get("file", ""), "tags": d.get("tags", [])
            })
    return sorted(stale, key=lambda x: -x["age_days"])


def format_decision(d: dict) -> str:
    """Format a decision for display."""
    lines = [f"[{d.get('seq', '???')}] {d.get('slug', 'unknown')} ({d.get('age_days', 0)}d ago, {d.get('status', '?')})"]
    if d.get("delta_files"):
        lines.append(f"  Delta: {', '.join(d['delta_files'][:3])}")
    if d.get("tags"):
        lines.append(f"  Tags: {', '.join(d['tags'])}")
    if d.get("parent"):
        lines.append(f"  Builds on: {d['parent']}")
    return '\n'.join(lines)


def format_decisions(results: list, limit: int = 10) -> str:
    """Format decisions for display."""
    if not results:
        return "No decisions found."
    return '\n\n'.join(format_decision(r) for r in results[:limit])


def get_memory_stats(memory: dict) -> dict:
    """Get memory statistics."""
    failures = memory.get("failures", [])
    discoveries = memory.get("discoveries", [])
    decisions = memory.get("decisions", {})
    return {
        "version": memory.get("version", "unknown"),
        "failures": {"count": len(failures), "total_cost": sum(f.get("cost", 0) for f in failures)},
        "discoveries": {"count": len(discoveries), "total_saved": sum(d.get("tokens_saved", 0) for d in discoveries)},
        "decisions": {"count": len(decisions), "complete": sum(1 for d in decisions.values() if d.get("status") == "complete")}
    }


def check_new_frameworks(memory: dict, campaign_frameworks: list[str]) -> list[str]:
    """Return frameworks not yet seen in memory.

    Used by synthesizer gate to determine if new framework learning is needed.

    Args:
        memory: Loaded memory dict
        campaign_frameworks: List of frameworks used in current campaign

    Returns:
        List of frameworks not found in memory's failure/discovery tags
    """
    # Collect all tags from failures and discoveries
    known_tags = set()
    for f in memory.get("failures", []):
        known_tags.update(t.lower() for t in f.get("tags", []))
    for d in memory.get("discoveries", []):
        known_tags.update(t.lower() for t in d.get("tags", []))

    # Filter to known framework tags
    known_frameworks = known_tags & KNOWN_FRAMEWORKS

    # Return frameworks in campaign that aren't in memory
    return [f for f in campaign_frameworks if f.lower() not in known_frameworks]


def add_source_to_patterns(memory: dict, campaign_id: str) -> dict:
    """Add campaign as source reference to existing patterns.

    Minimal tracking when synthesizer is skipped - just records that
    patterns were used in this campaign without full synthesis.

    Args:
        memory: Loaded memory dict
        campaign_id: Campaign identifier to add

    Returns:
        Updated memory dict
    """
    # Add to failures that were likely consulted
    for f in memory.get("failures", []):
        sources = f.get("source", [])
        if campaign_id not in sources:
            # Only add to patterns that have been used before
            if sources:
                f["source"] = sources + [campaign_id]

    # Add to discoveries that were likely applied
    for d in memory.get("discoveries", []):
        sources = d.get("source", [])
        if campaign_id not in sources:
            if sources:
                d["source"] = sources + [campaign_id]

    return memory


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(prog='memory', description='FTL unified memory')
    parser.add_argument('-b', '--base', type=Path, default=Path('.'))
    sub = parser.add_subparsers(dest='cmd')

    sub.add_parser('load')
    sub.add_parser('stats')
    context_p = sub.add_parser('context')
    context_p.add_argument('tags', nargs='?')
    inject_p = sub.add_parser('inject')
    inject_p.add_argument('tags', nargs='?')
    sub.add_parser('mine')
    query_p = sub.add_parser('query', aliases=['q'])
    query_p.add_argument('topic', nargs='?')
    dec_p = sub.add_parser('decision', aliases=['d'])
    dec_p.add_argument('seq')
    lin_p = sub.add_parser('lineage', aliases=['l'])
    lin_p.add_argument('seq')
    trace_p = sub.add_parser('trace', aliases=['t'])
    trace_p.add_argument('tag')
    impact_p = sub.add_parser('impact', aliases=['i'])
    impact_p.add_argument('file')
    age_p = sub.add_parser('age', aliases=['a'])
    age_p.add_argument('days', nargs='?', type=int, default=30)
    signal_p = sub.add_parser('signal', aliases=['s'])
    signal_p.add_argument('sign', choices=['+', '-'])
    signal_p.add_argument('id')

    # Synthesizer gate commands
    check_fw_p = sub.add_parser('check-new-frameworks', help='Check if frameworks are new to memory')
    check_fw_p.add_argument('frameworks', nargs='+', help='Frameworks to check (e.g., fasthtml fastapi)')

    add_src_p = sub.add_parser('add-source', help='Add campaign as source to existing patterns')
    add_src_p.add_argument('campaign_id', help='Campaign identifier')

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    memory_path = args.base / ".ftl" / "memory.json"

    if args.cmd == 'load':
        print(json.dumps(load_memory(memory_path), indent=2))
    elif args.cmd == 'stats':
        print(json.dumps(get_memory_stats(load_memory(memory_path)), indent=2))
    elif args.cmd == 'context':
        tags = args.tags.split(",") if args.tags else None
        print(json.dumps(get_context_for_task(load_memory(memory_path), tags), indent=2))
    elif args.cmd == 'inject':
        tags = args.tags.split(",") if args.tags else None
        print(format_for_injection(get_context_for_task(load_memory(memory_path), tags)))
    elif args.cmd == 'mine':
        workspace_dir = args.base / ".ftl" / "workspace"
        if not workspace_dir.exists():
            print(f"No workspace: {workspace_dir}", file=sys.stderr)
            sys.exit(1)
        memory = mine_workspace(workspace_dir, memory_path)
        print(f"Indexed {len(memory.get('decisions', {}))} decisions")
        for seq in sorted(memory.get("decisions", {}).keys()):
            d = memory["decisions"][seq]
            print(f"  [{seq}] {d['slug']} ({d['status']})")
    elif args.cmd in ('query', 'q'):
        memory = load_memory(memory_path)
        results = query_decisions(args.topic, memory)
        print(f"Decisions{' for ' + repr(args.topic) if args.topic else ''}:\n")
        print(format_decisions(results))
    elif args.cmd in ('decision', 'd'):
        memory = load_memory(memory_path)
        d = get_decision(args.seq, memory)
        if not d:
            print(f"Not found: {args.seq}")
            sys.exit(1)
        d["age_days"] = int((time.time() - d.get("mtime", 0)) / 86400)
        print(format_decision(d))
        if d.get("delivered"):
            print(f"\nDelivered:\n{d['delivered']}")
    elif args.cmd in ('lineage', 'l'):
        memory = load_memory(memory_path)
        chain = get_lineage(args.seq, memory)
        if not chain:
            print(f"Not found: {args.seq}")
            sys.exit(1)
        print(f"Lineage: {' → '.join(chain)}")
        for seq in chain:
            d = memory.get("decisions", {}).get(seq, {})
            print(f"  [{seq}] {d.get('slug', '?')} ({d.get('status', '?')})")
    elif args.cmd in ('trace', 't'):
        results = trace_tag(args.tag, load_memory(memory_path))
        if not results:
            print(f"No decisions using {args.tag}")
        else:
            print(f"Decisions using {args.tag}:\n")
            for r in results:
                print(f"  [{r['seq']}] {r['slug']} ({r['age_days']}d, {r['status']})")
    elif args.cmd in ('impact', 'i'):
        results = impact_file(args.file, load_memory(memory_path))
        if not results:
            print(f"No decisions affecting {args.file}")
        else:
            print(f"Decisions affecting '{args.file}':\n")
            for r in results:
                print(f"  [{r['seq']}] {r['slug']} ({r['age_days']}d)")
    elif args.cmd in ('age', 'a'):
        stale = find_stale(args.days, load_memory(memory_path))
        print(f"Stale (>{args.days}d):\n")
        for s in stale:
            print(f"  [{s['seq']}] {s['slug']} ({s['age_days']}d)")
    elif args.cmd in ('signal', 's'):
        memory = load_memory(memory_path)
        memory = add_signal(memory, args.id, args.sign)
        save_memory(memory, memory_path)
        entity = next((f for f in memory.get("failures", []) if f.get("id") == args.id), None)
        if not entity:
            entity = next((d for d in memory.get("discoveries", []) if d.get("id") == args.id), None)
        if entity:
            print(f"Signal: {args.id} -> {entity.get('signal', 0)}")
        else:
            print(f"Not found: {args.id}")

    elif args.cmd == 'check-new-frameworks':
        memory = load_memory(memory_path)
        new_fw = check_new_frameworks(memory, args.frameworks)
        if new_fw:
            # Output new frameworks (non-empty = synthesizer should run)
            print(" ".join(new_fw))
        # Empty output = all frameworks known, skip synthesizer

    elif args.cmd == 'add-source':
        memory = load_memory(memory_path)
        memory = add_source_to_patterns(memory, args.campaign_id)
        save_memory(memory, memory_path)
        print(f"Added source '{args.campaign_id}' to existing patterns")


if __name__ == "__main__":
    main()
