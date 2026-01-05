#!/usr/bin/env python3
"""lattice - Context graph for workspace decision traces.

Evolution: Decisions are primary. Patterns are edges.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# Bootstrap: ensure lib/ is in path when run directly
_lib_dir = Path(__file__).parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

# Now imports work whether run as module or script
from concepts import expand_query

LATTICE_DIR = ".ftl"
MEMORY_FILE = "memory.json"
MEMORY_VERSION = 2

# V1 files (for migration only)
INDEX_FILE = "index.json"
EDGES_FILE = "edges.json"
SIGNALS_FILE = "signals.json"

TAG_PATTERN = re.compile(r'(#(?:pattern|constraint|decision|antipattern|connection)/[\w-]+)')
FILENAME_PATTERN = re.compile(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$')


# --- Storage ---

def ensure_lattice_dir(base: Path = Path(".")) -> Path:
    """Ensure .ftl directory exists."""
    lattice = base / LATTICE_DIR
    lattice.mkdir(parents=True, exist_ok=True)
    return lattice


# --- V1 Storage (deprecated, kept for migration) ---

def load_index(base: Path = Path(".")) -> dict:
    """[V1 DEPRECATED] Load decision index. Use load_memory() instead."""
    path = base / LATTICE_DIR / INDEX_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {"decisions": {}, "patterns": {}}


def save_index(index: dict, base: Path = Path(".")):
    """[V1 DEPRECATED] Save decision index. Use save_memory() instead."""
    lattice = ensure_lattice_dir(base)
    (lattice / INDEX_FILE).write_text(json.dumps(index, indent=2))


def load_edges(base: Path = Path(".")) -> dict:
    """[V1 DEPRECATED] Load relationship edges. Use load_memory() instead."""
    path = base / LATTICE_DIR / EDGES_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {"lineage": {}, "pattern_use": {}, "file_impact": {}}


def save_edges(edges: dict, base: Path = Path(".")):
    """[V1 DEPRECATED] Save relationship edges. Use save_memory() instead."""
    lattice = ensure_lattice_dir(base)
    (lattice / EDGES_FILE).write_text(json.dumps(edges, indent=2))


def load_signals(base: Path = Path(".")) -> dict:
    """[V1 DEPRECATED] Load outcome signals. Use load_memory() instead."""
    path = base / LATTICE_DIR / SIGNALS_FILE
    if path.exists():
        return json.loads(path.read_text())
    return {}


def save_signals(signals: dict, base: Path = Path(".")):
    """[V1 DEPRECATED] Save outcome signals. Use save_memory() instead."""
    lattice = ensure_lattice_dir(base)
    (lattice / SIGNALS_FILE).write_text(json.dumps(signals, indent=2))


# --- Unified Memory (v2) ---

def _migrate_to_v2(base: Path = Path(".")) -> dict:
    """Migrate v1 files (index+edges+signals) to v2 memory.json."""
    # Load v1 files using old functions
    index = load_index(base)
    edges = load_edges(base)
    signals = load_signals(base)

    # Merge signals into patterns
    patterns = index.get("patterns", {})
    for tag, sig_data in signals.items():
        if tag not in patterns:
            patterns[tag] = {"decisions": [], "signals": [], "net": 0, "last": 0}
        patterns[tag]["signals"] = sig_data.get("signals", [])
        patterns[tag]["net"] = sig_data.get("net", 0)
        patterns[tag]["last"] = sig_data.get("last", 0)

    # Create v2 structure
    memory = {
        "version": MEMORY_VERSION,
        "mined": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decisions": index.get("decisions", {}),
        "patterns": patterns,
        "edges": edges
    }

    return memory


def _cleanup_v1_files(base: Path = Path(".")):
    """Remove v1 files after successful migration."""
    lattice = base / LATTICE_DIR
    for fname in [INDEX_FILE, EDGES_FILE, SIGNALS_FILE]:
        path = lattice / fname
        if path.exists():
            path.unlink()


def load_memory(base: Path = Path(".")) -> dict:
    """Load unified memory, migrating from v1 if needed."""
    lattice = base / LATTICE_DIR
    memory_path = lattice / MEMORY_FILE

    # Check for v2 format
    if memory_path.exists():
        memory = json.loads(memory_path.read_text())
        if memory.get("version") == MEMORY_VERSION:
            return memory

    # Check for v1 files and migrate
    index_path = lattice / INDEX_FILE
    if index_path.exists():
        print("  Migrating v1 memory to v2...", file=sys.stderr)
        memory = _migrate_to_v2(base)
        save_memory(memory, base)
        _cleanup_v1_files(base)
        print("  Migration complete.", file=sys.stderr)
        return memory

    # Empty memory
    return {
        "version": MEMORY_VERSION,
        "mined": None,
        "decisions": {},
        "patterns": {},
        "edges": {"lineage": {}, "pattern_use": {}, "file_impact": {}}
    }


def save_memory(memory: dict, base: Path = Path(".")):
    """Save unified memory."""
    lattice = ensure_lattice_dir(base)
    memory["version"] = MEMORY_VERSION
    (lattice / MEMORY_FILE).write_text(json.dumps(memory, indent=2))


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

    # Extract semantic memory fields (v2)
    rationale = extract_section(content, "Rationale")
    concepts_raw = extract_section(content, "Concepts")
    concepts = [c.strip() for c in concepts_raw.split(",")] if concepts_raw else []
    failure_modes = extract_section(content, "Failure modes")
    success_conditions = extract_section(content, "Success conditions")

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
        # Semantic memory (v2)
        "rationale": rationale,
        "concepts": concepts,
        "failure_modes": failure_modes,
        "success_conditions": success_conditions,
    }


# --- Mining ---

def mine_workspace(workspace: Path = Path("workspace"), base: Path = Path(".")) -> dict:
    """Build decision index from workspace files."""
    # Load existing memory to preserve signal history
    existing = load_memory(base)
    existing_patterns = existing.get("patterns", {})

    decisions = {}
    patterns = defaultdict(lambda: {"decisions": [], "signals": [], "net": 0, "last": 0})

    for path in sorted(workspace.glob("*.md")):
        parsed = parse_workspace_file(path)
        if not parsed:
            print(f"skip: {path.name} (naming)", file=sys.stderr)
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
            # Semantic memory (v2)
            "rationale": parsed.get("rationale", ""),
            "concepts": parsed.get("concepts", []),
            "failure_modes": parsed.get("failure_modes", ""),
            "success_conditions": parsed.get("success_conditions", ""),
        }

        # Build pattern index, preserving signal history
        for tag in parsed["tags"]:
            # Preserve existing signals if pattern already known
            if tag in existing_patterns and tag not in patterns:
                patterns[tag]["signals"] = existing_patterns[tag].get("signals", [])
                patterns[tag]["net"] = existing_patterns[tag].get("net", 0)
                patterns[tag]["last"] = existing_patterns[tag].get("last", 0)
            if seq not in patterns[tag]["decisions"]:
                patterns[tag]["decisions"].append(seq)

    # Build edges
    edges = build_edges(decisions)

    # Create unified memory
    memory = {
        "version": MEMORY_VERSION,
        "mined": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decisions": decisions,
        "patterns": dict(patterns),
        "edges": edges
    }
    save_memory(memory, base)

    # Embed decisions for semantic search (v2)
    try:
        from embeddings import EmbeddingStore
        store = EmbeddingStore(base / LATTICE_DIR)
        embeddings_available = store.available
    except ImportError:
        embeddings_available = False
        store = None

    if embeddings_available:
        # Read full content (not truncated) for embedding
        full_decisions = {}
        for seq, d in decisions.items():
            filepath = workspace / d["file"]
            if filepath.exists():
                content = filepath.read_text()
                full_decisions[seq] = {
                    **d,
                    "traces": extract_section(content, "Thinking Traces") or "",
                }

        embedded_count = store.embed_decisions(full_decisions)
        print(f"  Embedded {embedded_count} decisions")
    else:
        print("  (Embeddings disabled - install sentence-transformers)")

    return memory


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
    memory = load_memory(base)
    patterns = memory.get("patterns", {})

    if pattern not in patterns:
        patterns[pattern] = {"decisions": [], "signals": [], "net": 0, "last": 0}

    patterns[pattern]["signals"].append(signal)
    patterns[pattern]["net"] = patterns[pattern]["signals"].count("+") - patterns[pattern]["signals"].count("-")
    patterns[pattern]["last"] = int(time.time())

    memory["patterns"] = patterns
    save_memory(memory, base)

    return patterns[pattern]


# --- Queries ---

def calculate_score(mtime: float, signals: dict, pattern: str) -> float:
    """Calculate weighted score for a pattern."""
    days_old = (time.time() - mtime) / 86400
    recency_factor = 1 / (1 + days_old / 30)

    net_signals = signals.get(pattern, {}).get("net", 0)
    signal_factor = 1 + (net_signals * 0.2)

    return recency_factor * max(0.1, signal_factor)


def calculate_hybrid_score(decision: dict, signals: dict, is_exact: bool, semantic_score: float) -> float:
    """Calculate hybrid score combining recency, signals, and semantic similarity.

    Exact matches get semantic=1.0. Semantic-only matches get their similarity score.
    This ensures grep behavior is preserved while semantic matches surface when relevant.
    """
    days_old = (time.time() - decision.get("mtime", 0)) / 86400
    recency_factor = 1 / (1 + days_old / 30)

    # Signal factor from best pattern
    max_signal = 0
    for tag in decision.get("tags", []):
        net = signals.get(tag, {}).get("net", 0)
        max_signal = max(max_signal, net)
    signal_factor = 1 + (max_signal * 0.2)

    # Semantic factor: exact matches get full weight
    semantic_factor = 1.0 if is_exact else semantic_score

    return recency_factor * max(0.1, signal_factor) * semantic_factor


def query_decisions(topic: str = None, base: Path = Path(".")) -> list:
    """Query decisions, optionally filtered by topic.

    Uses hybrid retrieval: exact matches + semantic similarity (v2).
    """
    memory = load_memory(base)
    decisions = memory.get("decisions", {})
    patterns = memory.get("patterns", {})  # patterns contain signal data

    # No topic - return all decisions ranked by recency
    if not topic:
        results = []
        for seq, d in decisions.items():
            age_days = int((time.time() - d["mtime"]) / 86400)
            results.append({
                "seq": seq,
                "slug": d.get("slug", ""),
                "status": d.get("status", ""),
                "parent": d.get("parent"),
                "age_days": age_days,
                "score": calculate_score(d["mtime"], patterns, ""),
                "path": d.get("path", ""),
                "delta": d.get("delta", ""),
                "tags": d.get("tags", []),
                "file": d.get("file", ""),
            })
        return sorted(results, key=lambda x: -x["score"])

    # Expand topic to related concepts
    expanded_topics = expand_query(topic)

    # Find exact matches (existing behavior)
    exact_matches = set()
    for seq, d in decisions.items():
        searchable = " ".join([
            d.get('slug', ''),
            d.get('path', ''),
            d.get('traces', ''),
            d.get('rationale', ''),
            ' '.join(d.get('concepts', [])),
            ' '.join(d.get('tags', [])),
        ]).lower()

        if any(t in searchable for t in expanded_topics):
            exact_matches.add(seq)

    # Get semantic matches (v2)
    semantic_results = {}
    try:
        from embeddings import EmbeddingStore
        store = EmbeddingStore(base / LATTICE_DIR)
        if store.available:
            semantic_results = dict(store.query(topic, top_k=20))
    except ImportError:
        pass  # Graceful degradation - use exact matches only

    # Merge exact and semantic matches
    all_seqs = exact_matches | set(semantic_results.keys())

    results = []
    for seq in all_seqs:
        if seq not in decisions:
            continue

        d = decisions[seq]
        is_exact = seq in exact_matches
        semantic_score = semantic_results.get(seq, 0.5 if is_exact else 0)

        # Filter low-relevance semantic-only matches
        if not is_exact and semantic_score < 0.5:
            continue

        # Calculate hybrid score
        score = calculate_hybrid_score(d, patterns, is_exact, semantic_score)
        age_days = int((time.time() - d["mtime"]) / 86400)

        results.append({
            "seq": seq,
            "slug": d.get("slug", ""),
            "status": d.get("status", ""),
            "parent": d.get("parent"),
            "age_days": age_days,
            "score": score,
            "path": d.get("path", ""),
            "delta": d.get("delta", ""),
            "tags": d.get("tags", []),
            "file": d.get("file", ""),
            "match_type": "exact" if is_exact else "semantic",
        })

    return sorted(results, key=lambda x: -x["score"])


def get_decision(seq: str, base: Path = Path(".")) -> dict:
    """Get full decision record by sequence number."""
    memory = load_memory(base)
    seq = seq.zfill(3)
    return memory.get("decisions", {}).get(seq)


def get_lineage(seq: str, base: Path = Path(".")) -> list:
    """Get ancestry chain for a decision."""
    memory = load_memory(base)
    decisions = memory.get("decisions", {})

    chain = []
    current = seq.zfill(3)
    while current and current in decisions:
        chain.append(current)
        current = decisions[current].get("parent")
    chain.reverse()

    return chain


def trace_pattern(pattern: str, base: Path = Path(".")) -> list:
    """Find all decisions that used a pattern."""
    memory = load_memory(base)
    edges = memory.get("edges", {})
    decisions = memory.get("decisions", {})

    decision_seqs = edges.get("pattern_use", {}).get(pattern, [])

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
    memory = load_memory(base)
    edges = memory.get("edges", {})
    decisions = memory.get("decisions", {})

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
    memory = load_memory(base)
    threshold = time.time() - (days * 86400)

    stale = []
    for seq, d in memory.get("decisions", {}).items():
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

    parser = argparse.ArgumentParser(prog='lattice', description='Context graph for workspace decisions')
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
        memory = load_memory(args.base)
        if args.topic:
            print(f"Decisions for '{args.topic}':\n")
        else:
            print("All decisions (ranked):\n")
        print(format_decisions(results, signals=memory.get("patterns", {})))

    elif args.cmd in ('decision', 'd'):
        d = get_decision(args.seq, args.base)
        if not d:
            print(f"Decision {args.seq} not found")
            return
        memory = load_memory(args.base)
        d["seq"] = args.seq.zfill(3)
        d["age_days"] = int((time.time() - d["mtime"]) / 86400)
        print(format_decision(d, memory.get("patterns", {})))
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
        memory = load_memory(args.base)
        for seq in chain:
            d = memory.get("decisions", {}).get(seq, {})
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
