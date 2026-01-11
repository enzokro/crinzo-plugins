#!/usr/bin/env python3
"""lattice - Context graph for workspace decision traces.

Evolution: Decisions are primary. Patterns are edges.
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from collections import defaultdict

# Bootstrap: ensure lib/ is in path when run directly
_lib_dir = Path(__file__).parent
if str(_lib_dir) not in sys.path:
    sys.path.insert(0, str(_lib_dir))

# Now imports work whether run as module or script
from concepts import expand_query
# Import memory.py for unified memory operations
import memory as memory_module

LATTICE_DIR = ".ftl"
MEMORY_FILE = "graph.json"  # Separate from memory.json to avoid schema conflicts
MEMORY_VERSION = 3  # v3: Experiences are primary, patterns derived

# Re-export memory functions for compatibility
# The primary memory.json (failures/discoveries) is managed by memory_module
# This module manages graph.json (decisions/patterns/lineage)

# Legacy files (for migration only)
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


def _migrate_to_v3(memory: dict) -> dict:
    """Migrate v2 memory to v3 (experience-centric).

    v3 changes:
    - experiences: Primary structure (symptom → diagnosis → prevention → recovery)
    - checkpoints: Pre-flight checks derived from experiences
    - escalation_triggers: When to stop trying
    - patterns: Kept but secondary, derived from experiences
    """
    # Seed experiences from known failure modes
    experiences = {}
    checkpoints = {}

    # Convert high-signal patterns to experiences
    patterns = memory.get("patterns", {})
    for tag, data in patterns.items():
        net = data.get("net", 0)
        if net >= 3:  # Only significant patterns
            # Create experience from pattern
            exp_id = f"exp-{len(experiences) + 1:03d}"
            name = tag.split("/")[-1] if "/" in tag else tag

            experiences[exp_id] = {
                "name": name,
                "symptom": data.get("description", f"Issue related to {name}"),
                "diagnosis": data.get("description", ""),
                "prevention": {
                    "pre_flight": data.get("prevention", ""),
                    "checkpoint": data.get("success_conditions", ""),
                },
                "recovery": {
                    "symptom_match": "",
                    "action": data.get("prevention", ""),
                },
                "cost_when_missed": "",
                "source": f"migrated from {tag}",
                "derived_pattern": name,
                "signal": net,
            }

    # Default escalation triggers (tightened based on V8-V10 data)
    escalation_triggers = {
        "exploration-saturation": {
            "signal": "2 consecutive verification failures without matching known failure modes",
            "interpretation": "Pattern-environment mismatch, not debugging",
            "action": "Block with discovery needed message"
        },
        "tool-budget-exceeded": {
            "signal": "5 total tool calls without successful verification",
            "interpretation": "If not solved in 5 tools, exploring not debugging",
            "action": "Block immediately"
        },
        "repeated-same-error": {
            "signal": "Same error type appears 2+ times after attempted fix",
            "interpretation": "Fix attempt not addressing root cause",
            "action": "Block, require different approach"
        }
    }

    # Create v3 structure
    return {
        "version": MEMORY_VERSION,
        "mined": memory.get("mined"),
        "campaign": memory.get("campaign", ""),
        "experiences": experiences,
        "checkpoints": checkpoints,
        "escalation_triggers": escalation_triggers,
        "decisions": memory.get("decisions", {}),
        "patterns": patterns,  # Kept for backward compatibility
        "edges": memory.get("edges", {}),
        "meta_patterns": memory.get("meta_patterns", {}),
    }


def load_memory(base: Path = Path(".")) -> dict:
    """Load unified memory, migrating from older versions if needed."""
    lattice = base / LATTICE_DIR
    memory_path = lattice / MEMORY_FILE

    # Check for current version
    if memory_path.exists():
        memory = json.loads(memory_path.read_text())
        if memory.get("version") == MEMORY_VERSION:
            return memory

        # Migrate v2 to v3
        if memory.get("version") == 2:
            print("  Migrating v2 memory to v3 (experience-centric)...", file=sys.stderr)
            memory = _migrate_to_v3(memory)
            save_memory(memory, base)
            print("  Migration complete.", file=sys.stderr)
            return memory

    # Check for v1 files and migrate through v2 to v3
    index_path = lattice / INDEX_FILE
    if index_path.exists():
        print("  Migrating v1 memory to v3...", file=sys.stderr)
        memory = _migrate_to_v2(base)
        memory = _migrate_to_v3(memory)
        save_memory(memory, base)
        _cleanup_v1_files(base)
        print("  Migration complete.", file=sys.stderr)
        return memory

    # Empty v3 memory
    return {
        "version": MEMORY_VERSION,
        "mined": None,
        "campaign": "",
        "experiences": {},
        "checkpoints": {},
        "escalation_triggers": {
            "exploration-saturation": {
                "signal": "2 consecutive verification failures without matching known failure modes",
                "interpretation": "Pattern-environment mismatch, not debugging",
                "action": "Block with discovery needed message"
            },
            "tool-budget-exceeded": {
                "signal": "5 total tool calls without successful verification",
                "interpretation": "If not solved in 5 tools, exploring not debugging",
                "action": "Block immediately"
            },
            "repeated-same-error": {
                "signal": "Same error type appears 2+ times after attempted fix",
                "interpretation": "Fix attempt not addressing root cause",
                "action": "Block, require different approach"
            }
        },
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


def parse_options_considered(content: str) -> list:
    """Parse Options Considered section into structured list."""
    section = extract_section(content, "Options Considered")
    if not section:
        return []

    options = []
    # Match numbered options: "1. option — outcome (reason)"
    for match in re.finditer(r'^\d+\.\s*(.+?)(?:\s*[-—]\s*\*?\*?(\w+)\*?\*?)?(?:\s*\(([^)]+)\))?$',
                             section, re.MULTILINE):
        choice = match.group(1).strip()
        outcome = match.group(2).lower() if match.group(2) else ""
        reason = match.group(3) or ""

        # Normalize outcome
        if "chosen" in outcome or "**chosen**" in choice.lower():
            outcome = "chosen"
        elif "reject" in outcome:
            outcome = "rejected"

        options.append({
            "choice": choice,
            "outcome": outcome,
            "reason": reason
        })

    return options


def parse_precedent_used(content: str) -> list:
    """Extract patterns/constraints referenced in Precedent section."""
    section = extract_section(content, "Precedent")
    if not section:
        return []

    # Find all tags mentioned in Precedent
    return list(set(TAG_PATTERN.findall(section)))


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

    # Extract full structure (Implementation section)
    path_content = extract_section(content, "Path")
    delta_content = extract_section(content, "Delta")
    traces_content = extract_section(content, "Thinking Traces")
    delivered_content = extract_section(content, "Delivered")

    # Extract decision-centric fields (Phase D)
    question = extract_section(content, "Question")
    decision = extract_section(content, "Decision")
    options = parse_options_considered(content)
    precedent_used = parse_precedent_used(content)

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
        # Decision-centric (Phase D)
        "question": question,
        "decision": decision,
        "options": options,
        "precedent_used": precedent_used,
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


def parse_workspace_xml(path: Path) -> dict:
    """Parse XML workspace file into decision record."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
    except ET.ParseError:
        return None

    m = FILENAME_PATTERN.match(path.stem)
    if not m:
        return None

    seq, slug, status, parent = m.groups()
    mtime = path.stat().st_mtime

    # Extract from XML elements
    delta_files = [d.text for d in root.findall('.//implementation/delta') if d.text]
    delta_content = ', '.join(delta_files)
    verify = root.findtext('.//verify', '')

    # Delivered
    delivered_elem = root.find('.//delivered')
    delivered_content = delivered_elem.text if delivered_elem is not None and delivered_elem.text else ''

    # Framework idioms
    idioms_elem = root.find('.//framework_idioms')
    framework = idioms_elem.get('framework', '') if idioms_elem is not None else ''

    # Tags from patterns and failures
    tags = []
    for p in root.findall('.//pattern'):
        name = p.get('name')
        if name:
            tags.append(f"#pattern/{name}")
    for f in root.findall('.//failure'):
        name = f.get('name')
        if name:
            tags.append(f"#failure/{name}")

    # Lineage
    lineage = root.find('.//lineage')
    prior_delivery = lineage.findtext('prior_delivery', '') if lineage is not None else ''

    return {
        "seq": seq,
        "slug": slug,
        "status": status,
        "parent": parent,
        "mtime": mtime,
        "file": path.name,
        # Decision-centric
        "question": "",
        "decision": "",
        "options": [],
        "precedent_used": [],
        # Full structure
        "path": verify,
        "delta": delta_content,
        "delta_files": delta_files,
        "traces": "",
        "delivered": delivered_content,
        "tags": tags,
        # Semantic memory
        "rationale": "",
        "concepts": [],
        "failure_modes": "",
        "success_conditions": "",
        # XML-specific
        "framework": framework,
        "prior_delivery": prior_delivery,
    }


# --- Mining ---

def mine_workspace(workspace: Path = Path(".ftl/workspace"), base: Path = Path(".")) -> dict:
    """Build decision index from workspace files."""
    # Load existing memory to preserve signal history
    existing = load_memory(base)
    existing_patterns = existing.get("patterns", {})

    decisions = {}
    patterns = defaultdict(lambda: {"decisions": [], "signals": [], "net": 0, "last": 0})

    for path in sorted(workspace.glob("*.xml")):
        parsed = parse_workspace_xml(path)
        if not parsed:
            print(f"skip: {path.name} (naming or parse error)", file=sys.stderr)
            continue

        seq = parsed["seq"]

        # Store full decision record
        decisions[seq] = {
            "file": parsed["file"],
            "slug": parsed["slug"],
            "mtime": parsed["mtime"],
            "status": parsed["status"],
            "parent": parsed["parent"],
            # Decision-centric (Phase D)
            "question": parsed.get("question", ""),
            "decision": parsed.get("decision", ""),
            "options": parsed.get("options", []),
            "precedent_used": parsed.get("precedent_used", []),
            # Implementation
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

    # Detect meta-patterns (pattern clusters that co-occur)
    meta_patterns = detect_meta_patterns(dict(patterns), decisions)

    # Preserve existing v3 fields or initialize
    existing = load_memory(base)
    experiences = existing.get("experiences", {})
    checkpoints = existing.get("checkpoints", {})
    escalation_triggers = existing.get("escalation_triggers", {
        "exploration-saturation": {
            "signal": "2 consecutive verification failures without matching known failure modes",
            "interpretation": "Pattern-environment mismatch, not debugging",
            "action": "Block with discovery needed message"
        },
        "tool-budget-exceeded": {
            "signal": "5 total tool calls without successful verification",
            "interpretation": "If not solved in 5 tools, exploring not debugging",
            "action": "Block immediately"
        },
        "repeated-same-error": {
            "signal": "Same error type appears 2+ times after attempted fix",
            "interpretation": "Fix attempt not addressing root cause",
            "action": "Block, require different approach"
        }
    })

    # Create unified memory (v3)
    memory = {
        "version": MEMORY_VERSION,
        "mined": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "campaign": existing.get("campaign", ""),
        "experiences": experiences,
        "checkpoints": checkpoints,
        "escalation_triggers": escalation_triggers,
        "decisions": decisions,
        "patterns": dict(patterns),
        "edges": edges,
        "meta_patterns": meta_patterns
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


def detect_meta_patterns(patterns: dict, decisions: dict) -> dict:
    """Detect pattern clusters that co-occur in 2+ decisions.

    Meta-patterns are compositions of simpler patterns that appear together.
    Their combined signal indicates reliability of the composition.
    """
    from collections import Counter

    # Build co-occurrence matrix
    co_occur = Counter()
    for dec_id, dec in decisions.items():
        tags = dec.get("tags", [])
        # Only consider pattern tags (not constraints, decisions, etc.)
        pattern_tags = [t for t in tags if t.startswith("#pattern/")]
        for i, t1 in enumerate(pattern_tags):
            for t2 in pattern_tags[i+1:]:
                # Normalize order for consistent keys
                pair = tuple(sorted([t1, t2]))
                co_occur[pair] += 1

    # Extract meta-patterns where co-occurrence >= 2
    meta_patterns = {}
    for (t1, t2), count in co_occur.items():
        if count >= 2:
            # Create readable name from pattern slugs
            slug1 = t1.split("/")[-1]
            slug2 = t2.split("/")[-1]
            name = f"{slug1}+{slug2}"

            # Combined signal is sum of component signals
            net1 = patterns.get(t1, {}).get("net", 0)
            net2 = patterns.get(t2, {}).get("net", 0)
            net = net1 + net2

            # Only include if combined signal is positive
            if net > 0:
                meta_patterns[name] = {
                    "components": [t1, t2],
                    "co_occurrences": count,
                    "net": net
                }

    return meta_patterns


# --- Planner/Router Query Functions ---

def query_for_planner(memory: dict) -> str:
    """Format patterns for planner consumption.

    Returns markdown-formatted prior knowledge sorted by signal strength.
    """
    lines = ["## Prior Knowledge (from graph.json)", ""]

    # Patterns by signal strength (descending)
    patterns = sorted(
        memory.get("patterns", {}).items(),
        key=lambda x: x[1].get("net", 0),
        reverse=True
    )

    positive_patterns = [(tag, data) for tag, data in patterns if data.get("net", 0) > 0]
    if positive_patterns:
        lines.append("### Patterns")
        for tag, data in positive_patterns:
            net = data.get("net", 0)
            lines.append(f"- {tag} (+{net})")

    # Meta-patterns
    meta = memory.get("meta_patterns", {})
    if meta:
        lines.append("")
        lines.append("### Meta-Patterns")
        sorted_meta = sorted(meta.items(), key=lambda x: x[1].get("net", 0), reverse=True)
        for name, data in sorted_meta:
            components = " + ".join(data.get("components", []))
            lines.append(f"- {name}: {components} (net: +{data.get('net', 0)})")

    if len(lines) == 2:  # Only header, no content
        return "## Prior Knowledge\nNo patterns accumulated yet."

    return "\n".join(lines)


def warnings_for_delta(memory: dict, delta_files: list) -> str:
    """Extract CRITICAL warnings relevant to delta files.

    Returns warnings for patterns with |net| >= 3 that are
    relevant to the files being modified.

    Checks three sources:
    1. Pattern's warn_for field (for seeded patterns)
    2. edges.file_impact (for seeded edges)
    3. decisions.delta_files (for patterns discovered during runs)
    """
    if not delta_files:
        return "No applicable pattern warnings (no delta files specified)"

    warnings = []
    delta_lower = [df.lower() for df in delta_files]

    for tag, data in memory.get("patterns", {}).items():
        net = data.get("net", 0)
        if abs(net) < 3:  # Only patterns with significant signal
            continue

        matched = False

        # Source 1: Pattern's own warn_for field (from accumulator seed)
        warn_for = data.get("warn_for", [])
        for trigger in warn_for:
            trigger_lower = trigger.lower()
            for df in delta_lower:
                if trigger_lower in df or df in trigger_lower:
                    matched = True
                    break
            if matched:
                break

        # Source 2: Check via decisions if not matched yet
        if not matched:
            for dec_id in data.get("decisions", []):
                dec = memory.get("decisions", {}).get(dec_id, {})
                dec_files = dec.get("delta_files", [])

                for df in delta_lower:
                    for dec_file in dec_files:
                        if df in dec_file.lower() or dec_file.lower() in df:
                            matched = True
                            break
                    if matched:
                        break
                if matched:
                    break

        if matched:
            sign = "+" if net > 0 else ""
            desc = data.get("description", "")
            prevention = data.get("prevention", "")
            if prevention:
                warnings.append(f"CRITICAL: {tag} ({sign}{net})\n  Prevention: {prevention}")
            elif desc:
                warnings.append(f"CRITICAL: {tag} ({sign}{net})\n  {desc}")
            else:
                warnings.append(f"CRITICAL: {tag} ({sign}{net})")

    # Source 3: Check file_impact edges
    edges = memory.get("edges", {})
    file_impact = edges.get("file_impact", {})
    for trigger, pattern_tags in file_impact.items():
        trigger_lower = trigger.lower()
        for df in delta_lower:
            if trigger_lower in df or df in trigger_lower:
                for tag in pattern_tags:
                    if tag in memory.get("patterns", {}):
                        data = memory["patterns"][tag]
                        net = data.get("net", 0)
                        if abs(net) >= 3 and tag not in [w.split("(")[0].replace("CRITICAL: ", "").strip() for w in warnings]:
                            sign = "+" if net > 0 else ""
                            prevention = data.get("prevention", "")
                            if prevention:
                                warnings.append(f"CRITICAL: {tag} ({sign}{net})\n  Prevention: {prevention}")
                            else:
                                warnings.append(f"CRITICAL: {tag} ({sign}{net})")

    if not warnings:
        return "No applicable pattern warnings"

    # Sort by absolute signal value (most critical first)
    def sort_key(w):
        try:
            # Extract number from "(+7)" or "(-3)"
            num_str = w.split("(")[1].split(")")[0]
            return -abs(int(num_str.replace("+", "")))
        except:
            return 0

    return "\n".join(sorted(set(warnings), key=sort_key))


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


# --- Experiences (v3) ---

def add_experience(experience: dict, base: Path = Path(".")) -> str:
    """Add a new experience to memory.

    Experience structure:
    {
        "name": "fastlite-api-mismatch",
        "symptom": "AttributeError: db has no attribute 'insert'",
        "diagnosis": "FastLite uses db.t.tablename.insert(), not db.insert()",
        "prevention": {
            "pre_flight": "Check FastLite documentation pattern",
            "checkpoint": "All db operations use db.t.{table}.{method}() format"
        },
        "recovery": {
            "symptom_match": "AttributeError.*db.*insert",
            "action": "Change db.insert(X) to db.t.tablename.insert(X)"
        },
        "cost_when_missed": "1004K tokens",
        "source": "anki-v8 task 003"
    }
    """
    memory = load_memory(base)
    experiences = memory.get("experiences", {})

    # Generate next experience ID
    exp_nums = [int(k.split("-")[1]) for k in experiences.keys() if k.startswith("exp-")]
    next_num = max(exp_nums) + 1 if exp_nums else 1
    exp_id = f"exp-{next_num:03d}"

    # Add timestamp
    experience["created"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    experiences[exp_id] = experience
    memory["experiences"] = experiences
    save_memory(memory, base)

    return exp_id


def add_checkpoint(name: str, checkpoint: dict, base: Path = Path(".")) -> str:
    """Add a pre-flight checkpoint to memory.

    Checkpoint structure:
    {
        "applies_when": "delta includes date fields",
        "check": "All date.today() calls use .isoformat()",
        "command": "grep -E 'date\\.today\\(\\)' --include='*.py' | grep -v isoformat",
        "expected": "No output",
        "if_fails": "Add .isoformat() to date comparisons",
        "from_experience": "exp-002"  # optional
    }
    """
    memory = load_memory(base)
    checkpoints = memory.get("checkpoints", {})

    checkpoints[name] = checkpoint
    memory["checkpoints"] = checkpoints
    save_memory(memory, base)

    return name


def get_experiences_for_delta(memory: dict, delta_files: list) -> list:
    """Get relevant experiences for delta files.

    Returns experiences whose prevention or recovery might apply.
    """
    if not delta_files:
        return []

    experiences = memory.get("experiences", {})
    delta_lower = " ".join(delta_files).lower()

    relevant = []
    for exp_id, exp in experiences.items():
        # Check if experience is relevant based on source or name
        source = exp.get("source", "").lower()
        name = exp.get("name", "").lower()

        # Simple relevance: experience name or source mentions similar files/concepts
        if any(df.lower() in source or df.lower() in name for df in delta_files):
            relevant.append({"id": exp_id, **exp})
            continue

        # Check if prevention mentions relevant files
        prevention = exp.get("prevention", {})
        if isinstance(prevention, dict):
            pre_flight = prevention.get("pre_flight", "").lower()
            checkpoint = prevention.get("checkpoint", "").lower()
            if any(df.lower() in pre_flight or df.lower() in checkpoint for df in delta_files):
                relevant.append({"id": exp_id, **exp})

    return relevant


def get_checkpoints_for_delta(memory: dict, delta_files: list) -> list:
    """Get applicable checkpoints for delta files.

    Returns checkpoints whose applies_when matches the delta.
    """
    if not delta_files:
        return []

    checkpoints = memory.get("checkpoints", {})
    delta_str = " ".join(delta_files).lower()

    applicable = []
    for name, checkpoint in checkpoints.items():
        applies_when = checkpoint.get("applies_when", "").lower()

        # Simple matching: check if applies_when keywords are in delta
        keywords = ["date", "database", "fastlite", "route", "test", "api"]
        for kw in keywords:
            if kw in applies_when and kw in delta_str:
                applicable.append({"name": name, **checkpoint})
                break

        # Or if applies_when mentions a delta file type
        if ".py" in applies_when and any(f.endswith(".py") for f in delta_files):
            if name not in [c["name"] for c in applicable]:
                applicable.append({"name": name, **checkpoint})

    return applicable


def format_experiences_for_builder(memory: dict, delta_files: list) -> str:
    """Format experiences and checkpoints for builder consumption.

    Returns markdown with pre-flight checks and known failure modes.
    """
    lines = []

    # Get relevant experiences
    experiences = get_experiences_for_delta(memory, delta_files)
    checkpoints = get_checkpoints_for_delta(memory, delta_files)

    # Pre-flight checks
    if checkpoints:
        lines.append("## Pre-flight Checks")
        lines.append("Before running Verify, confirm:")
        for cp in checkpoints:
            lines.append(f"- [ ] {cp.get('check', cp['name'])}")
            if cp.get("command"):
                lines.append(f"      Command: `{cp['command']}`")
        lines.append("")

    # Known failure modes from experiences
    if experiences:
        lines.append("## Known Failure Modes")
        lines.append("| Symptom | Diagnosis | Action |")
        lines.append("|---------|-----------|--------|")
        for exp in experiences:
            symptom = exp.get("symptom", "")[:40]
            diagnosis = exp.get("diagnosis", "")[:30]
            recovery = exp.get("recovery", {})
            action = recovery.get("action", "")[:30] if isinstance(recovery, dict) else ""
            lines.append(f"| {symptom} | {diagnosis} | {action} |")
        lines.append("")

    # Escalation triggers
    triggers = memory.get("escalation_triggers", {})
    if triggers:
        lines.append("## Escalation Protocol")
        for name, trigger in triggers.items():
            lines.append(f"- **{name}**: {trigger.get('signal', '')}")
            lines.append(f"  Action: {trigger.get('action', '')}")

    if not lines:
        return "No applicable experiences or checkpoints."

    return "\n".join(lines)


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

    # Use question as title if available, else slug
    title = d.get("question") or slug
    lines = [f"[{seq}] {title[:60]} ({age}d ago, {status})"]

    # Show decision if available
    if d.get("decision"):
        lines.append(f"  Decision: {d['decision'][:80]}")

    # Show rejected options if available
    rejected = [o for o in d.get("options", []) if o.get("outcome") == "rejected"]
    if rejected:
        rejected_strs = [f"{o['choice'][:30]} ({o['reason'][:20]})" if o.get('reason') else o['choice'][:40]
                        for o in rejected[:3]]
        lines.append(f"  Rejected: {', '.join(rejected_strs)}")

    if d.get("path"):
        lines.append(f"  Path: {d['path'][:80]}")

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


def format_for_injection(results: list, signals: dict = None, limit: int = 5) -> str:
    """Format query results for injection into workspace Precedent section.

    Returns a ready-to-paste markdown block for the router to inject.
    """
    if not results:
        return "## Precedent\nNo relevant prior decisions."

    signals = signals or {}

    # Collect related decisions
    related = []
    for r in results[:limit]:
        seq = r.get("seq", "???")
        slug = r.get("slug", "unknown")
        parent = r.get("parent")
        suffix = f" (from {parent})" if parent else ""
        related.append(f"[{seq}] {slug}{suffix}")

    # Collect patterns/antipatterns/constraints with signals
    patterns = []
    antipatterns = []
    constraints = []

    seen_tags = set()
    for r in results[:limit]:
        for tag in r.get("tags", []):
            if tag in seen_tags:
                continue
            seen_tags.add(tag)

            net = signals.get(tag, {}).get("net", 0)
            if net > 0:
                tag_str = f"{tag} (+{net})"
            elif net < 0:
                tag_str = f"{tag} ({net})"
            else:
                tag_str = tag

            if tag.startswith("#pattern/"):
                patterns.append(tag_str)
            elif tag.startswith("#antipattern/"):
                antipatterns.append(tag_str)
            elif tag.startswith("#constraint/"):
                constraints.append(tag_str)

    # Build output
    lines = ["## Precedent"]
    lines.append(f"Related: {', '.join(related)}")

    if patterns:
        lines.append(f"Patterns: {', '.join(patterns)}")
    if antipatterns:
        lines.append(f"Antipatterns: {', '.join(antipatterns)}")
    if constraints:
        lines.append(f"Constraints: {', '.join(constraints)}")

    return '\n'.join(lines)


# --- CLI ---

def main():
    import argparse

    parser = argparse.ArgumentParser(prog='lattice', description='Context graph for workspace decisions')
    parser.add_argument('-w', '--workspace', type=Path, default=Path('.ftl/workspace'))
    parser.add_argument('-b', '--base', type=Path, default=Path('.'))

    sub = parser.add_subparsers(dest='cmd')

    # Mine
    sub.add_parser('mine', help='Build decision index from workspace')

    # Query
    query_p = sub.add_parser('query', aliases=['q'], help='Query decisions')
    query_p.add_argument('topic', nargs='?', help='Topic to filter by')
    query_p.add_argument('--format', choices=['human', 'inject', 'planner'], default='human',
                         help='Output format: human (default), inject (for workspace precedent), or planner (for planner prior knowledge)')

    # Warnings (for router)
    warn_p = sub.add_parser('warnings', aliases=['w'], help='Get pattern warnings for delta files')
    warn_p.add_argument('--delta', required=True, help='Comma-separated list of delta files')

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

    # Experiences (v3)
    exp_p = sub.add_parser('experiences', aliases=['e'], help='List experiences for delta files')
    exp_p.add_argument('--delta', help='Comma-separated list of delta files')

    # Checkpoints (v3)
    check_p = sub.add_parser('checkpoints', aliases=['c'], help='List checkpoints for delta files')
    check_p.add_argument('--delta', help='Comma-separated list of delta files')

    # Builder context (v3) - combined experiences + checkpoints + escalation
    builder_p = sub.add_parser('builder-context', aliases=['bc'], help='Get full builder context for delta')
    builder_p.add_argument('--delta', required=True, help='Comma-separated list of delta files')

    args = parser.parse_args()

    if not args.cmd:
        parser.print_help()
        return

    if args.cmd == 'mine':
        index = mine_workspace(args.workspace, args.base)
        n_decisions = len(index.get("decisions", {}))
        n_patterns = len(index.get("patterns", {}))
        n_meta = len(index.get("meta_patterns", {}))
        print(f"Indexed {n_decisions} decisions, {n_patterns} patterns, {n_meta} meta-patterns from {args.workspace}")
        for seq in sorted(index.get("decisions", {}).keys()):
            d = index["decisions"][seq]
            print(f"  [{seq}] {d['slug']} ({d['status']})")

    elif args.cmd in ('query', 'q'):
        memory = load_memory(args.base)

        if args.format == 'planner':
            # Output prior knowledge for planner consumption
            print(query_for_planner(memory))
        elif args.format == 'inject':
            # Output ready-to-paste Precedent section for workspace
            results = query_decisions(args.topic, args.base)
            print(format_for_injection(results, signals=memory.get("patterns", {})))
        else:
            results = query_decisions(args.topic, args.base)
            if args.topic:
                print(f"Decisions for '{args.topic}':\n")
            else:
                print("All decisions (ranked):\n")
            print(format_decisions(results, signals=memory.get("patterns", {})))

    elif args.cmd in ('warnings', 'w'):
        memory = load_memory(args.base)
        delta_files = [f.strip() for f in args.delta.split(",") if f.strip()]
        print(warnings_for_delta(memory, delta_files))

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

    elif args.cmd in ('experiences', 'e'):
        memory = load_memory(args.base)
        if args.delta:
            delta_files = [f.strip() for f in args.delta.split(",") if f.strip()]
            experiences = get_experiences_for_delta(memory, delta_files)
        else:
            experiences = [{"id": k, **v} for k, v in memory.get("experiences", {}).items()]

        if not experiences:
            print("No experiences found.")
        else:
            print(f"Experiences ({len(experiences)}):\n")
            for exp in experiences:
                print(f"  [{exp.get('id', '?')}] {exp.get('name', 'unnamed')}")
                print(f"    Symptom: {exp.get('symptom', '')[:60]}")
                if exp.get('recovery', {}).get('action'):
                    print(f"    Action: {exp['recovery']['action'][:60]}")
                print()

    elif args.cmd in ('checkpoints', 'c'):
        memory = load_memory(args.base)
        if args.delta:
            delta_files = [f.strip() for f in args.delta.split(",") if f.strip()]
            checkpoints = get_checkpoints_for_delta(memory, delta_files)
        else:
            checkpoints = [{"name": k, **v} for k, v in memory.get("checkpoints", {}).items()]

        if not checkpoints:
            print("No checkpoints found.")
        else:
            print(f"Checkpoints ({len(checkpoints)}):\n")
            for cp in checkpoints:
                print(f"  [{cp['name']}]")
                print(f"    Check: {cp.get('check', '')[:60]}")
                if cp.get('command'):
                    print(f"    Command: {cp['command'][:60]}")
                print()

    elif args.cmd in ('builder-context', 'bc'):
        memory = load_memory(args.base)
        delta_files = [f.strip() for f in args.delta.split(",") if f.strip()]
        print(format_experiences_for_builder(memory, delta_files))


if __name__ == '__main__':
    main()
