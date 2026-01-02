#!/usr/bin/env python3
"""ctx - Context graph for workspace decision traces."""

import json
import re
import sys
import time
from pathlib import Path
from collections import defaultdict

CTX_DIR = ".ctx"
INDEX_FILE = "index.json"
SIGNALS_FILE = "signals.json"

TAG_PATTERN = re.compile(r'^(#(?:pattern|constraint|decision|antipattern|connection)/[\w-]+)', re.MULTILINE)
FILENAME_PATTERN = re.compile(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$')


def ensure_ctx_dir(base: Path = Path(".")) -> Path:
    """Ensure .ctx directory exists."""
    ctx = base / CTX_DIR
    ctx.mkdir(parents=True, exist_ok=True)
    return ctx


def load_index(base: Path = Path(".")) -> dict:
    """Load pattern index."""
    path = base / CTX_DIR / INDEX_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_index(index: dict, base: Path = Path(".")):
    """Save pattern index."""
    ctx = ensure_ctx_dir(base)
    (ctx / INDEX_FILE).write_text(json.dumps(index, indent=2))


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


def parse_workspace_file(path: Path) -> dict:
    """Parse a workspace file for metadata and tags."""
    content = path.read_text()
    m = FILENAME_PATTERN.match(path.stem)

    if not m:
        return None

    seq, slug, status, parent = m.groups()
    mtime = path.stat().st_mtime

    # Calculate depth
    depth = 1
    if parent:
        depth += 1  # Simplified; full depth requires parsing all files

    # Extract tags
    tags = TAG_PATTERN.findall(content)

    # Extract context around each tag (line before and after)
    tag_contexts = {}
    lines = content.split('\n')
    for i, line in enumerate(lines):
        for tag in TAG_PATTERN.findall(line):
            context_lines = []
            if i > 0:
                context_lines.append(lines[i-1].strip())
            context_lines.append(lines[i].strip())
            if i < len(lines) - 1:
                context_lines.append(lines[i+1].strip())
            tag_contexts[tag] = ' | '.join(filter(None, context_lines))

    return {
        "seq": seq,
        "slug": slug,
        "status": status,
        "parent": parent,
        "mtime": mtime,
        "depth": depth,
        "tags": tags,
        "contexts": tag_contexts,
        "path": path.name
    }


def mine_workspace(workspace: Path = Path("workspace"), base: Path = Path(".")) -> dict:
    """Extract patterns from all workspace files."""
    index = {}

    for path in sorted(workspace.glob("*.md")):
        parsed = parse_workspace_file(path)
        if not parsed:
            continue

        for tag in parsed["tags"]:
            index[tag] = {
                "source": parsed["path"],
                "mtime": parsed["mtime"],
                "depth": parsed["depth"],
                "context": parsed["contexts"].get(tag, ""),
                "status": parsed["status"]
            }

    save_index(index, base)
    return index


def add_signal(pattern: str, signal: str, base: Path = Path(".")):
    """Add outcome signal (+/-) to a pattern."""
    signals = load_signals(base)

    if pattern not in signals:
        signals[pattern] = {"signals": [], "net": 0, "last": 0}

    signals[pattern]["signals"].append(signal)
    signals[pattern]["net"] = signals[pattern]["signals"].count("+") - signals[pattern]["signals"].count("-")
    signals[pattern]["last"] = int(time.time())

    save_signals(signals, base)
    return signals[pattern]


def calculate_score(mtime: float, signals: dict, pattern: str) -> float:
    """Calculate weighted score for a pattern."""
    days_old = (time.time() - mtime) / 86400
    recency_factor = 1 / (1 + days_old / 30)

    net_signals = signals.get(pattern, {}).get("net", 0)
    signal_factor = 1 + (net_signals * 0.2)

    return recency_factor * signal_factor


def find_stale(days: int = 30, base: Path = Path(".")) -> list:
    """Find patterns older than threshold."""
    index = load_index(base)
    threshold = time.time() - (days * 86400)

    stale = []
    for pattern, data in index.items():
        if data["mtime"] < threshold:
            age_days = int((time.time() - data["mtime"]) / 86400)
            stale.append({
                "pattern": pattern,
                "age_days": age_days,
                "source": data["source"]
            })

    return sorted(stale, key=lambda x: -x["age_days"])


def query_patterns(topic: str = None, base: Path = Path(".")) -> list:
    """Query patterns, optionally filtered by topic."""
    index = load_index(base)
    signals = load_signals(base)

    results = []
    for pattern, data in index.items():
        # Simple substring match for topic
        if topic and topic.lower() not in pattern.lower() and topic.lower() not in data.get("context", "").lower():
            continue

        score = calculate_score(data["mtime"], signals, pattern)
        age_days = int((time.time() - data["mtime"]) / 86400)
        net = signals.get(pattern, {}).get("net", 0)

        results.append({
            "pattern": pattern,
            "score": score,
            "age_days": age_days,
            "net_signals": net,
            "source": data["source"],
            "context": data.get("context", "")
        })

    return sorted(results, key=lambda x: -x["score"])


def format_pattern_output(results: list, limit: int = 10) -> str:
    """Format pattern results for display."""
    if not results:
        return "No patterns found."

    lines = []
    for r in results[:limit]:
        signal_str = f"+{r['net_signals']}" if r['net_signals'] > 0 else str(r['net_signals']) if r['net_signals'] < 0 else ""
        signal_part = f", {signal_str}" if signal_str else ""
        lines.append(f"  {r['pattern']} ({r['age_days']}d{signal_part}) from {r['source']}")
        if r['context']:
            lines.append(f"    {r['context'][:80]}...")

    return '\n'.join(lines)


# CLI interface
def main():
    import argparse

    parser = argparse.ArgumentParser(prog='ctx', description='Context graph for workspace')
    parser.add_argument('-w', '--workspace', type=Path, default=Path('workspace'))
    parser.add_argument('-b', '--base', type=Path, default=Path('.'))

    sub = parser.add_subparsers(dest='cmd')

    mine_p = sub.add_parser('mine', help='Extract patterns from workspace')

    query_p = sub.add_parser('query', aliases=['q'], help='Query patterns')
    query_p.add_argument('topic', nargs='?', help='Topic to filter by')

    age_p = sub.add_parser('age', aliases=['a'], help='Find stale patterns')
    age_p.add_argument('days', nargs='?', type=int, default=30, help='Days threshold')

    signal_p = sub.add_parser('signal', aliases=['s'], help='Add outcome signal')
    signal_p.add_argument('sign', choices=['+', '-'], help='Signal type')
    signal_p.add_argument('pattern', help='Pattern to signal')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == 'mine':
        index = mine_workspace(args.workspace, args.base)
        print(f"Indexed {len(index)} patterns from {args.workspace}")
        for p in sorted(index.keys()):
            print(f"  {p}")

    elif args.cmd in ('query', 'q'):
        results = query_patterns(args.topic, args.base)
        if args.topic:
            print(f"Patterns matching '{args.topic}':")
        else:
            print("All patterns (ranked):")
        print(format_pattern_output(results))

    elif args.cmd in ('age', 'a'):
        stale = find_stale(args.days, args.base)
        print(f"Stale patterns (>{args.days}d):")
        for s in stale:
            print(f"  {s['pattern']} ({s['age_days']}d) from {s['source']}")

    elif args.cmd in ('signal', 's'):
        result = add_signal(args.pattern, args.sign, args.base)
        print(f"Signal added: {args.pattern} -> net {result['net']}")


if __name__ == '__main__':
    main()
