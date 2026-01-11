"""
FTL Memory - SAVE and LOAD interfaces

This module provides the memory interface for FTL's learning system.
Memory stores failures and discoveries that transfer between campaigns.

SAVE: Synthesizer extracts failures/discoveries from workspace → memory
LOAD: Router/Builder gets relevant context for task ← memory

Memory Format v3.0:
{
  "version": "3.0",
  "updated": "ISO date",
  "failures": [...],      # PRIMARY: what broke and how to fix/prevent
  "discoveries": [...]    # SECONDARY: non-obvious approaches that saved tokens
}

Schema changes from v2.0:
- "patterns" renamed to "discoveries" (higher bar for inclusion)
- Failures now use "trigger" instead of "symptom" (observable condition)
- Discoveries use "trigger", "insight", "evidence", "tokens_saved"
- All entries require cost/savings attribution
"""

import json
from pathlib import Path
from datetime import date
from typing import Optional


def load_memory(path: Path) -> dict:
    """Load memory file, migrate if needed, return empty structure if missing."""
    if not path.exists():
        return {"version": "3.0", "updated": date.today().isoformat(), "failures": [], "discoveries": []}

    memory = json.loads(path.read_text())

    # Migrate v2.0 → v3.0
    if memory.get("version", "2.0") == "2.0":
        memory = _migrate_v2_to_v3(memory)

    return memory


def _migrate_v2_to_v3(memory: dict) -> dict:
    """Migrate v2.0 memory to v3.0 format."""
    new_memory = {
        "version": "3.0",
        "updated": memory.get("updated", date.today().isoformat()),
        "failures": [],
        "discoveries": []
    }

    # Migrate patterns → discoveries (only high-signal ones)
    for p in memory.get("patterns", []):
        if p.get("signal", 1) >= 3:  # Only keep high-signal patterns
            discovery = {
                "id": p.get("id", f"d{len(new_memory['discoveries'])+1:03d}"),
                "name": p["name"],
                "trigger": p.get("when", ""),
                "insight": p.get("do", ""),
                "evidence": f"Signal {p.get('signal', 1)} from {len(p.get('source', []))} runs",
                "tokens_saved": p.get("signal", 1) * 10000,  # Estimate
                "tags": p.get("tags", []),
                "source": p.get("source", []),
                "created": p.get("created", date.today().isoformat()),
                "migrated_from_v2": True
            }
            new_memory["discoveries"].append(discovery)

    # Migrate failures (update field names)
    for f in memory.get("failures", []):
        failure = {
            "id": f.get("id", f"f{len(new_memory['failures'])+1:03d}"),
            "name": f["name"],
            "trigger": f.get("trigger", f.get("symptom", "")),  # Support both
            "fix": f.get("fix", ""),
            "match": f.get("match", ""),
            "prevent": f.get("prevent", ""),
            "cost": f.get("cost", 0),
            "tags": f.get("tags", []),
            "source": f.get("source", []),
            "created": f.get("created", date.today().isoformat())
        }
        new_memory["failures"].append(failure)

    return new_memory


def save_memory(memory: dict, path: Path) -> None:
    """Write memory file with updated timestamp."""
    memory["updated"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, indent=2))


# --- SAVE Interface ---

def add_failure(memory: dict, failure: dict) -> dict:
    """
    Add a failure mode.

    If failure with same name exists, merge sources and accumulate cost.
    Otherwise, add as new failure.

    Failure schema:
    {
      "name": str,       # required: failure slug
      "trigger": str,    # required: observable condition (error message, behavior)
      "fix": str,        # required: specific action that resolves it
      "match": str,      # required: regex to match in logs
      "prevent": str,    # required: command to run before verify (or explain why impossible)
      "cost": int,       # required: tokens spent on this failure
      "tags": [str],     # optional: for filtering
      "source": [str],   # optional: runs where discovered
    }
    """
    existing = next((f for f in memory.get("failures", []) if f["name"] == failure["name"]), None)

    if existing:
        existing["source"] = list(set(existing.get("source", []) + failure.get("source", [])))
        existing["cost"] = existing.get("cost", 0) + failure.get("cost", 0)
    else:
        if "failures" not in memory:
            memory["failures"] = []
        failure["id"] = f"f{len(memory['failures'])+1:03d}"
        failure["created"] = date.today().isoformat()
        if "tags" not in failure:
            failure["tags"] = []
        if "source" not in failure:
            failure["source"] = []
        memory["failures"].append(failure)

    return memory


def add_discovery(memory: dict, discovery: dict) -> dict:
    """
    Add a discovery (non-obvious approach that saved tokens).

    If discovery with same name exists, merge sources and evidence.
    Otherwise, add as new discovery.

    Discovery schema:
    {
      "name": str,           # required: discovery slug
      "trigger": str,        # required: when this applies
      "insight": str,        # required: the non-obvious thing
      "evidence": str,       # required: proof from trace that it worked
      "tokens_saved": int,   # required: estimated savings
      "tags": [str],         # optional: for filtering
      "source": [str],       # optional: runs where discovered
    }
    """
    existing = next((d for d in memory.get("discoveries", []) if d["name"] == discovery["name"]), None)

    if existing:
        existing["source"] = list(set(existing.get("source", []) + discovery.get("source", [])))
        existing["tokens_saved"] = existing.get("tokens_saved", 0) + discovery.get("tokens_saved", 0)
        # Append evidence (deduplicated)
        if discovery.get("evidence"):
            existing_evidence = existing.get("evidence", "")
            new_evidence = discovery["evidence"]
            # Dedupe: don't append if already contains this text
            if new_evidence not in existing_evidence:
                existing["evidence"] = existing_evidence + "; " + new_evidence
    else:
        if "discoveries" not in memory:
            memory["discoveries"] = []
        discovery["id"] = f"d{len(memory['discoveries'])+1:03d}"
        discovery["created"] = date.today().isoformat()
        if "tags" not in discovery:
            discovery["tags"] = []
        if "source" not in discovery:
            discovery["source"] = []
        memory["discoveries"].append(discovery)

    return memory


# Backwards compatibility alias
def add_pattern(memory: dict, pattern: dict) -> dict:
    """
    DEPRECATED: Use add_discovery instead.

    Converts old pattern format to discovery format.
    """
    discovery = {
        "name": pattern.get("name"),
        "trigger": pattern.get("when", pattern.get("trigger", "")),
        "insight": pattern.get("do", pattern.get("insight", "")),
        "evidence": pattern.get("evidence", "Migrated from pattern"),
        "tokens_saved": pattern.get("tokens_saved", pattern.get("signal", 1) * 10000),
        "tags": pattern.get("tags", []),
        "source": pattern.get("source", [])
    }
    return add_discovery(memory, discovery)


# --- LOAD Interface ---

def get_context_for_task(memory: dict, tags: Optional[list[str]] = None) -> dict:
    """
    Select relevant failures and discoveries for a task.

    If tags provided, filter to items matching any tag.
    If no tags, return all items.

    Returns failures sorted by cost (highest first).
    Returns discoveries sorted by tokens_saved (highest first).
    """
    def matches_tags(item):
        if not tags:
            return True
        item_tags = item.get("tags", [])
        return any(t in item_tags for t in tags)

    return {
        "failures": sorted(
            [f for f in memory.get("failures", []) if matches_tags(f)],
            key=lambda f: -f.get("cost", 0)
        ),
        "discoveries": sorted(
            [d for d in memory.get("discoveries", []) if matches_tags(d)],
            key=lambda d: -d.get("tokens_saved", 0)
        ),
        # Backwards compat
        "patterns": sorted(
            [d for d in memory.get("discoveries", []) if matches_tags(d)],
            key=lambda d: -d.get("tokens_saved", 0)
        ),
    }


def format_for_injection(context: dict) -> str:
    """
    Format context as markdown for agent injection.

    Output format prioritizes failures (the actual lessons):

    ## Known Failures (avoid these)
    - **name** (cost: Xk tokens)
      Trigger: what you'll see
      Fix: what to do
      Match: `regex`

    ## Pre-flight Checks
    Run before verify:
    - [ ] `command`

    ## Discoveries
    - **name** (saved: Xk tokens)
      When: trigger
      Insight: what to do
    """
    lines = []

    # Failures first - these are the actual lessons
    failures = context.get("failures", [])
    if failures:
        lines.append("## Known Failures (avoid these)\n")
        for f in failures:
            cost_k = f.get("cost", 0) // 1000
            lines.append(f"- **{f['name']}** (cost: {cost_k}k tokens)")
            lines.append(f"  Trigger: {f.get('trigger', f.get('symptom', 'unknown'))}")
            lines.append(f"  Fix: {f['fix']}")
            if f.get("match"):
                lines.append(f"  Match: `{f['match']}`")
            lines.append("")

        # Pre-flight checks from failure prevention
        preflights = [f for f in failures if f.get("prevent")]
        if preflights:
            lines.append("## Pre-flight Checks\n")
            lines.append("Run before verify:")
            for f in preflights:
                lines.append(f"- [ ] `{f['prevent']}` ({f['name']})")
            lines.append("")

    # Discoveries second
    discoveries = context.get("discoveries", context.get("patterns", []))
    if discoveries:
        lines.append("## Discoveries\n")
        for d in discoveries:
            saved_k = d.get("tokens_saved", d.get("signal", 1) * 10) // 1000
            lines.append(f"- **{d['name']}** (saved: {saved_k}k tokens)")
            lines.append(f"  When: {d.get('trigger', d.get('when', 'unknown'))}")
            lines.append(f"  Insight: {d.get('insight', d.get('do', 'unknown'))}")
            lines.append("")

    return "\n".join(lines)


def inject_and_log(
    memory: dict,
    run_id: str,
    tags: Optional[list[str]] = None,
    log_path: Optional[Path] = None
) -> tuple[str, dict]:
    """
    Format injection AND create tracking log.

    This is the primary entry point for memory injection - it combines
    formatting for agent consumption AND tracking for evaluation.

    Returns:
        tuple of (markdown_text, injection_log)
    """
    context = get_context_for_task(memory, tags)
    markdown = format_for_injection(context)

    # Track what was injected
    failure_ids = [f["id"] for f in context.get("failures", [])]
    discovery_ids = [d["id"] for d in context.get("discoveries", [])]

    log = create_injection_log(
        run_id,
        memory,
        failure_ids,
        discovery_ids,
        tags_matched=tags
    )

    if log_path:
        save_injection_log(log, log_path)

    return markdown, log


# --- Injection Logging (for evaluation) ---

def create_injection_log(
    run_id: str,
    memory: dict,
    injected_failures: list[str],
    injected_discoveries: list[str],
    delta_files: Optional[list[str]] = None,
    tags_matched: Optional[list[str]] = None,
) -> dict:
    """
    Create injection log for evaluation.

    Records what was available vs what was injected.
    Utilization is tracked separately after run completes.
    """
    return {
        "run_id": run_id,
        "timestamp": date.today().isoformat(),
        "memory_version": memory.get("version", "3.0"),
        "delta": delta_files or [],
        "tags_matched": tags_matched or [],
        "failures": {
            "available": [f["id"] for f in memory.get("failures", [])],
            "injected": injected_failures,
            "matched": []  # filled after run by evaluator
        },
        "discoveries": {
            "available": [d["id"] for d in memory.get("discoveries", [])],
            "injected": injected_discoveries,
            "utilized": []  # filled after run by evaluator
        },
        "preflights": {
            "ran": [],
            "passed": [],
            "failed": []
        }
    }


def save_injection_log(log: dict, path: Path) -> None:
    """Save injection log to evidence directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(log, indent=2))


# --- Memory Statistics ---

def get_memory_stats(memory: dict) -> dict:
    """Get statistics about memory health."""
    failures = memory.get("failures", [])
    discoveries = memory.get("discoveries", [])

    return {
        "version": memory.get("version", "unknown"),
        "failures": {
            "count": len(failures),
            "with_prevent": sum(1 for f in failures if f.get("prevent")),
            "with_match": sum(1 for f in failures if f.get("match")),
            "total_cost": sum(f.get("cost", 0) for f in failures),
        },
        "discoveries": {
            "count": len(discoveries),
            "with_evidence": sum(1 for d in discoveries if d.get("evidence")),
            "total_saved": sum(d.get("tokens_saved", 0) for d in discoveries),
        },
        "health": _calculate_health(failures, discoveries)
    }


def _calculate_health(failures: list, discoveries: list) -> str:
    """Calculate memory health rating."""
    if not failures and not discoveries:
        return "empty"

    # Failures should have prevent commands
    if failures:
        prevent_ratio = sum(1 for f in failures if f.get("prevent")) / len(failures)
        if prevent_ratio < 0.5:
            return "incomplete (most failures lack prevent commands)"

    # Should have more failures than discoveries (learning is failure-driven)
    if discoveries and not failures:
        return "suspicious (discoveries without failures)"

    if len(failures) >= len(discoveries):
        return "healthy"

    return "pattern-heavy (consider pruning low-value discoveries)"


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python memory.py <command> [args]")
        print("Commands:")
        print("  load <path>              - Load and display memory")
        print("  stats <path>             - Show memory statistics")
        print("  context <path> [tags]    - Get context for tags")
        print("  inject <path> [tags]     - Format injection markdown")
        print("  migrate <path>           - Migrate v2.0 to v3.0")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "load":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        memory = load_memory(path)
        print(json.dumps(memory, indent=2))

    elif cmd == "stats":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        memory = load_memory(path)
        stats = get_memory_stats(memory)
        print(json.dumps(stats, indent=2))

    elif cmd == "context":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        tags = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        memory = load_memory(path)
        context = get_context_for_task(memory, tags)
        print(json.dumps(context, indent=2))

    elif cmd == "inject":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        tags = sys.argv[3].split(",") if len(sys.argv) > 3 else None
        memory = load_memory(path)
        context = get_context_for_task(memory, tags)
        print(format_for_injection(context))

    elif cmd == "migrate":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        memory = load_memory(path)  # Auto-migrates
        save_memory(memory, path)
        print(f"Migrated to v{memory['version']}")
        print(json.dumps(get_memory_stats(memory), indent=2))

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
