#!/usr/bin/env python3
"""ctx v2.0 - Context graph for workspace decision traces.

Evolution: Decisions are primary. Patterns are edges.
"""

import json
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

CTX_DIR = ".ctx"
INDEX_FILE = "index.json"
EDGES_FILE = "edges.json"
SIGNALS_FILE = "signals.json"

TAG_PATTERN = re.compile(r'(#(?:pattern|constraint|decision|antipattern|connection)/[\w-]+)')
FILENAME_PATTERN = re.compile(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$')


# --- Storage ---

def ensure_ctx_dir(base: Path = Path(".")) -> Path:
    """Ensure .ctx directory exists."""
    ctx = base / CTX_DIR
    ctx.mkdir(parents=True, exist_ok=True)
    return ctx


def load_index(base: Path = Path(".")) -> dict:
    """Load decision index."""
    path = base / CTX_DIR / INDEX_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {"decisions": {}, "patterns": {}}


def save_index(index: dict, base: Path = Path(".")):
    """Save decision index."""
    ctx = ensure_ctx_dir(base)
    (ctx / INDEX_FILE).write_text(json.dumps(index, indent=2))


def load_edges(base: Path = Path(".")) -> dict:
    """Load relationship edges."""
    path = base / CTX_DIR / EDGES_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {"lineage": {}, "pattern_use": {}, "file_impact": {}}


def save_edges(edges: dict, base: Path = Path(".")):
    """Save relationship edges."""
    ctx = ensure_ctx_dir(base)
    (ctx / EDGES_FILE).write_text(json.dumps(edges, indent=2))


def load_signals(base: Path = Path(".")) -> dict:
    """Load outcome signals."""
    path = base / CTX_DIR / SIGNALS_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_signals(signals: dict, base: Path = Path(".")):
    """Save outcome signals."""
    ctx = ensure_ctx_dir(base)
    (ctx / SIGNALS_FILE).write_text(json.dumps(signals, indent=2))


# --- Parsing ---

def extract_section(content: str, section_name: str) -> str:
    """Extract content after a section header."""
    # Match "Path:" or "## Thinking Traces" style headers
    patterns = [
        rf'^{section_name}:\s*(.+?)(?=\n[A-Z]|\n##|\n\n##|\Z)',  # "Path: content"
        rf'^##\s*{section_name}\s*\n(.*?)(?=\n##|\Z)',  # "## Section\ncontent"
    ]

    for pattern in patterns:
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return ""


def parse_delta_patterns(delta: str) -> list:
    """Parse file patterns from Delta string."""
    if not delta:
        return []

    # Extract file patterns like "src/auth/*.ts" or "lib/ctx.py"
    patterns = []
    for part in re.split(r'[,\s]+', delta):
        part = part.strip('`[]')
        if part and ('/' in part or '*' in part or part.endswith('.py') or part.endswith('.ts') or part.endswith('.md')):
            patterns.append(part)

    return patterns


def parse_workspace_file(path: Path) -> dict:
    """Parse full decision record from workspace file."""
    content = path.read_text()
    m = FILENAME_PATTERN.match(path.stem)

    if not m:
        return None

    seq, slug, status, parent = m.groups()
    mtime = path.stat().st_mtime

    # Extract tags
    tags = list(set(TAG_PATTERN.findall(content)))

    # Extract full structure
    path_content = extract_section(content, "Path")
    delta_content = extract_section(content, "Delta")
    traces_content = extract_section(content, "Thinking Traces")
    delivered_content = extract_section(content, "Delivered")

    # Parse Delta into file patterns
    delta_files = parse_delta_patterns(delta_content)

    return {
        "seq": seq,
        "slug": slug,
        "status": status,
        "parent": parent,
        "mtime": mtime,
        "file": path.name,
        # Full structure
        "path": path_content,
        "delta": delta_content,
        "delta_files": delta_files,
        "traces": traces_content,
        "delivered": delivered_content,
        "tags": tags,
    }


# --- Mining ---

def mine_workspace(workspace: Path = Path("workspace"), base: Path = Path(".")) -> dict:
    """Build decision index from workspace files."""
    decisions = {}
    patterns = defaultdict(lambda: {"decisions": [], "signals": [], "net": 0})

    for path in sorted(workspace.glob("*.md")):
        parsed = parse_workspace_file(path)
        if not parsed:
            continue

        seq = parsed["seq"]

        # Store full decision record
        decisions[seq] = {
            "file": parsed["file"],
            "slug": parsed["slug"],
            "mtime": parsed["mtime"],
            "status": parsed["status"],
            "parent": parsed["parent"],
            "path": parsed["path"],
            "delta": parsed["delta"],
            "delta_files": parsed["delta_files"],
            "traces": parsed["traces"][:500] if parsed["traces"] else "",  # Truncate for index
            "delivered": parsed["delivered"][:500] if parsed["delivered"] else "",
            "tags": parsed["tags"],
        }

        # Build pattern index (inverse)
        for tag in parsed["tags"]:
            if seq not in patterns[tag]["decisions"]:
                patterns[tag]["decisions"].append(seq)

    # Merge with existing signals
    signals = load_signals(base)
    for tag, data in patterns.items():
        if tag in signals:
            data["signals"] = signals[tag].get("signals", [])
            data["net"] = signals[tag].get("net", 0)

    index = {"decisions": decisions, "patterns": dict(patterns)}
    save_index(index, base)

    # Build edges
    edges = build_edges(decisions)
    save_edges(edges, base)

    return index


def build_edges(decisions: dict) -> dict:
    """Derive relationships from decision records."""
    edges = {
        "lineage": {},       # decision -> parent chain
        "pattern_use": {},   # pattern -> [decisions]
        "file_impact": {},   # file pattern -> [decisions]
    }

    for seq, d in decisions.items():
        # Lineage
        if d.get("parent"):
            edges["lineage"][seq] = d["parent"]

        # Pattern use (inverse index)
        for tag in d.get("tags", []):
            edges["pattern_use"].setdefault(tag, [])
            if seq not in edges["pattern_use"][tag]:
                edges["pattern_use"][tag].append(seq)

        # File impact
        for pattern in d.get("delta_files", []):
            edges["file_impact"].setdefault(pattern, [])
            if seq not in edges["file_impact"][pattern]:
                edges["file_impact"][pattern].append(seq)

    return edges


# --- Signals ---

def add_signal(pattern: str, signal: str, base: Path = Path(".")):
    """Add outcome signal (+/-) to a pattern."""
    signals = load_signals(base)

    if pattern not in signals:
        signals[pattern] = {"signals": [], "net": 0, "last": 0}

    signals[pattern]["signals"].append(signal)
    signals[pattern]["net"] = signals[pattern]["signals"].count("+") - signals[pattern]["signals"].count("-")
    signals[pattern]["last"] = int(time.time())

    save_signals(signals, base)

    # Update index if exists
    index = load_index(base)
    if pattern in index.get("patterns", {}):
        index["patterns"][pattern]["signals"] = signals[pattern]["signals"]
        index["patterns"][pattern]["net"] = signals[pattern]["net"]
        save_index(index, base)

    return signals[pattern]


# --- Queries ---

def calculate_score(mtime: float, signals: dict, pattern: str) -> float:
    """Calculate weighted score for a pattern."""
    days_old = (time.time() - mtime) / 86400
    recency_factor = 1 / (1 + days_old / 30)

    net_signals = signals.get(pattern, {}).get("net", 0)
    signal_factor = 1 + (net_signals * 0.2)

    return recency_factor * max(0.1, signal_factor)


def query_decisions(topic: str = None, base: Path = Path(".")) -> list:
    """Query decisions, optionally filtered by topic."""
    index = load_index(base)
    signals = load_signals(base)

    results = []
    for seq, d in index.get("decisions", {}).items():
        # Topic matching: check slug, path, traces, tags
        if topic:
            topic_lower = topic.lower()
            searchable = f"{d.get('slug', '')} {d.get('path', '')} {d.get('traces', '')} {' '.join(d.get('tags', []))}".lower()
            if topic_lower not in searchable:
                continue

        # Calculate score based on patterns
        max_score = 0
        for tag in d.get("tags", []):
            score = calculate_score(d["mtime"], signals, tag)
            max_score = max(max_score, score)

        if not d.get("tags"):
            max_score = calculate_score(d["mtime"], signals, "")

        age_days = int((time.time() - d["mtime"]) / 86400)

        results.append({
            "seq": seq,
            "slug": d.get("slug", ""),
            "status": d.get("status", ""),
            "parent": d.get("parent"),
            "age_days": age_days,
            "score": max_score,
            "path": d.get("path", ""),
            "delta": d.get("delta", ""),
            "tags": d.get("tags", []),
            "file": d.get("file", ""),
        })

    return sorted(results, key=lambda x: -x["score"])


def get_decision(seq: str, base: Path = Path(".")) -> dict:
    """Get full decision record by sequence number."""
    index = load_index(base)
    seq = seq.zfill(3)
    return index.get("decisions", {}).get(seq)


def get_lineage(seq: str, base: Path = Path(".")) -> list:
    """Get ancestry chain for a decision."""
    index = load_index(base)
    decisions = index.get("decisions", {})

    chain = []
    current = seq.zfill(3)
    while current and current in decisions:
        chain.append(current)
        current = decisions[current].get("parent")
    chain.reverse()

    return chain


def trace_pattern(pattern: str, base: Path = Path(".")) -> list:
    """Find all decisions that used a pattern."""
    edges = load_edges(base)
    index = load_index(base)

    decision_seqs = edges.get("pattern_use", {}).get(pattern, [])
    decisions = index.get("decisions", {})

    results = []
    for seq in decision_seqs:
        if seq in decisions:
            d = decisions[seq]
            results.append({
                "seq": seq,
                "slug": d.get("slug", ""),
                "status": d.get("status", ""),
                "age_days": int((time.time() - d["mtime"]) / 86400),
                "file": d.get("file", ""),
            })

    return sorted(results, key=lambda x: x["seq"])


def impact_file(file_pattern: str, base: Path = Path(".")) -> list:
    """Find decisions that touched a file pattern."""
    edges = load_edges(base)
    index = load_index(base)
    decisions = index.get("decisions", {})

    results = []
    for pattern, seqs in edges.get("file_impact", {}).items():
        # Simple substring match
        if file_pattern.lower() in pattern.lower():
            for seq in seqs:
                if seq in decisions:
                    d = decisions[seq]
                    results.append({
                        "seq": seq,
                        "slug": d.get("slug", ""),
                        "status": d.get("status", ""),
                        "age_days": int((time.time() - d["mtime"]) / 86400),
                        "file": d.get("file", ""),
                        "delta": d.get("delta", ""),
                    })

    # Deduplicate by seq
    seen = set()
    unique = []
    for r in results:
        if r["seq"] not in seen:
            seen.add(r["seq"])
            unique.append(r)

    return sorted(unique, key=lambda x: x["seq"])


def find_stale(days: int = 30, base: Path = Path(".")) -> list:
    """Find decisions older than threshold."""
    index = load_index(base)
    threshold = time.time() - (days * 86400)

    stale = []
    for seq, d in index.get("decisions", {}).items():
        if d["mtime"] < threshold:
            age_days = int((time.time() - d["mtime"]) / 86400)
            stale.append({
                "seq": seq,
                "slug": d.get("slug", ""),
                "age_days": age_days,
                "file": d.get("file", ""),
                "tags": d.get("tags", []),
            })

    return sorted(stale, key=lambda x: -x["age_days"])


# --- Formatting ---

def format_decision(d: dict, signals: dict = None) -> str:
    """Format a single decision for display."""
    signals = signals or {}
    seq = d.get("seq", "???")
    slug = d.get("slug", "unknown")
    status = d.get("status", "?")
    age = d.get("age_days", 0)
    parent = d.get("parent")

    lines = [f"[{seq}] {slug} ({age}d ago, {status})"]

    if d.get("path"):
        lines.append(f"  Path: {d['path'][:80]}")

    if d.get("delta"):
        lines.append(f"  Delta: {d['delta'][:60]}")

    if d.get("tags"):
        tag_strs = []
        for tag in d["tags"]:
            net = signals.get(tag, {}).get("net", 0)
            if net > 0:
                tag_strs.append(f"{tag} (+{net})")
            elif net < 0:
                tag_strs.append(f"{tag} ({net})")
            else:
                tag_strs.append(tag)
        lines.append(f"  Tags: {', '.join(tag_strs)}")

    if parent:
        lines.append(f"  Builds on: {parent}")

    return '\n'.join(lines)


def format_decisions(results: list, limit: int = 10, signals: dict = None) -> str:
    """Format decision results for display."""
    if not results:
        return "No decisions found."

    signals = signals or {}
    output = []
    for r in results[:limit]:
        output.append(format_decision(r, signals))

    return '\n\n'.join(output)


# --- CLI ---

def main():
    import argparse

    parser = argparse.ArgumentParser(prog='ctx', description='Context graph for workspace decisions')
    parser.add_argument('-w', '--workspace', type=Path, default=Path('workspace'))
    parser.add_argument('-b', '--base', type=Path, default=Path('.'))

    sub = parser.add_subparsers(dest='cmd')

    # Mine
    sub.add_parser('mine', help='Build decision index from workspace')

    # Query
    query_p = sub.add_parser('query', aliases=['q'], help='Query decisions')
    query_p.add_argument('topic', nargs='?', help='Topic to filter by')

    # Decision
    dec_p = sub.add_parser('decision', aliases=['d'], help='Show full decision record')
    dec_p.add_argument('seq', help='Decision sequence number')

    # Lineage
    lin_p = sub.add_parser('lineage', aliases=['l'], help='Show decision ancestry')
    lin_p.add_argument('seq', help='Decision sequence number')

    # Trace
    trace_p = sub.add_parser('trace', aliases=['t'], help='Find decisions using a pattern')
    trace_p.add_argument('pattern', help='Pattern tag (e.g., #pattern/name)')

    # Impact
    impact_p = sub.add_parser('impact', aliases=['i'], help='Find decisions affecting a file')
    impact_p.add_argument('file', help='File pattern')

    # Age
    age_p = sub.add_parser('age', aliases=['a'], help='Find stale decisions')
    age_p.add_argument('days', nargs='?', type=int, default=30, help='Days threshold')

    # Signal
    signal_p = sub.add_parser('signal', aliases=['s'], help='Add outcome signal')
    signal_p.add_argument('sign', choices=['+', '-'], help='Signal type')
    signal_p.add_argument('pattern', help='Pattern to signal')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == 'mine':
        index = mine_workspace(args.workspace, args.base)
        n_decisions = len(index.get("decisions", {}))
        n_patterns = len(index.get("patterns", {}))
        print(f"Indexed {n_decisions} decisions, {n_patterns} patterns from {args.workspace}")
        for seq in sorted(index.get("decisions", {}).keys()):
            d = index["decisions"][seq]
            print(f"  [{seq}] {d['slug']} ({d['status']})")

    elif args.cmd in ('query', 'q'):
        results = query_decisions(args.topic, args.base)
        signals = load_signals(args.base)
        if args.topic:
            print(f"Decisions for '{args.topic}':\n")
        else:
            print("All decisions (ranked):\n")
        print(format_decisions(results, signals=signals))

    elif args.cmd in ('decision', 'd'):
        d = get_decision(args.seq, args.base)
        if not d:
            print(f"Decision {args.seq} not found")
            return
        signals = load_signals(args.base)
        d["seq"] = args.seq.zfill(3)
        d["age_days"] = int((time.time() - d["mtime"]) / 86400)
        print(format_decision(d, signals))
        if d.get("traces"):
            print(f"\nThinking Traces:\n{d['traces']}")
        if d.get("delivered"):
            print(f"\nDelivered:\n{d['delivered']}")

    elif args.cmd in ('lineage', 'l'):
        chain = get_lineage(args.seq, args.base)
        if not chain:
            print(f"Decision {args.seq} not found")
            return
        print(f"Lineage: {' → '.join(chain)}")
        index = load_index(args.base)
        for seq in chain:
            d = index.get("decisions", {}).get(seq, {})
            print(f"  [{seq}] {d.get('slug', '?')} ({d.get('status', '?')})")

    elif args.cmd in ('trace', 't'):
        results = trace_pattern(args.pattern, args.base)
        if not results:
            print(f"No decisions found using {args.pattern}")
            return
        print(f"Decisions using {args.pattern}:\n")
        for r in results:
            print(f"  [{r['seq']}] {r['slug']} ({r['age_days']}d, {r['status']})")

    elif args.cmd in ('impact', 'i'):
        results = impact_file(args.file, args.base)
        if not results:
            print(f"No decisions found affecting {args.file}")
            return
        print(f"Decisions affecting '{args.file}':\n")
        for r in results:
            print(f"  [{r['seq']}] {r['slug']} ({r['age_days']}d)")
            print(f"    Delta: {r['delta'][:60]}")

    elif args.cmd in ('age', 'a'):
        stale = find_stale(args.days, args.base)
        print(f"Stale decisions (>{args.days}d):\n")
        for s in stale:
            tags = ', '.join(s['tags'][:3]) if s['tags'] else 'no tags'
            print(f"  [{s['seq']}] {s['slug']} ({s['age_days']}d) - {tags}")

    elif args.cmd in ('signal', 's'):
        result = add_signal(args.pattern, args.sign, args.base)
        print(f"Signal added: {args.pattern} -> net {result['net']}")


if __name__ == '__main__':
    main()
