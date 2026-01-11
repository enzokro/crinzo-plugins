"""
FTL Memory - SAVE and LOAD interfaces

This module provides the memory interface for FTL's learning system.
Memory stores patterns and failures that transfer between campaigns.

SAVE: Synthesizer extracts patterns/failures from workspace → memory
LOAD: Router/Builder gets relevant context for task ← memory

Memory Format v2.0:
{
  "version": "2.0",
  "updated": "ISO date",
  "patterns": [...],
  "failures": [...]
}
"""

import json
from pathlib import Path
from datetime import date
from typing import Optional


def load_memory(path: Path) -> dict:
    """Load memory file, return empty structure if missing."""
    if not path.exists():
        return {"version": "2.0", "updated": date.today().isoformat(), "patterns": [], "failures": []}
    return json.loads(path.read_text())


def save_memory(memory: dict, path: Path) -> None:
    """Write memory file with updated timestamp."""
    memory["updated"] = date.today().isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, indent=2))


# --- SAVE Interface ---

def add_pattern(memory: dict, pattern: dict) -> dict:
    """
    Add or reinforce a pattern.

    If pattern with same name exists, increment signal and merge sources.
    Otherwise, add as new pattern with signal=1.

    Pattern schema:
    {
      "name": str,       # required: pattern slug
      "when": str,       # required: trigger condition
      "do": str,         # required: action to take
      "tags": [str],     # optional: for filtering
      "source": [str],   # optional: runs that contributed
    }
    """
    existing = next((p for p in memory["patterns"] if p["name"] == pattern["name"]), None)

    if existing:
        existing["signal"] = min(10, existing.get("signal", 1) + 1)
        existing["source"] = list(set(existing.get("source", []) + pattern.get("source", [])))
    else:
        pattern["id"] = f"p{len(memory['patterns'])+1:03d}"
        pattern["signal"] = pattern.get("signal", 1)
        pattern["created"] = date.today().isoformat()
        if "tags" not in pattern:
            pattern["tags"] = []
        if "source" not in pattern:
            pattern["source"] = []
        memory["patterns"].append(pattern)

    return memory


def add_failure(memory: dict, failure: dict) -> dict:
    """
    Add a failure mode.

    If failure with same name exists, merge sources and accumulate cost.
    Otherwise, add as new failure.

    Failure schema:
    {
      "name": str,       # required: failure slug
      "symptom": str,    # required: what you observe
      "fix": str,        # required: recovery action
      "match": str,      # optional: regex to match errors
      "prevent": str,    # optional: pre-flight check command
      "cost": int,       # optional: tokens wasted
      "tags": [str],     # optional: for filtering
      "source": [str],   # optional: runs where discovered
    }
    """
    existing = next((f for f in memory["failures"] if f["name"] == failure["name"]), None)

    if existing:
        existing["source"] = list(set(existing.get("source", []) + failure.get("source", [])))
        existing["cost"] = existing.get("cost", 0) + failure.get("cost", 0)
    else:
        failure["id"] = f"f{len(memory['failures'])+1:03d}"
        if "tags" not in failure:
            failure["tags"] = []
        if "source" not in failure:
            failure["source"] = []
        memory["failures"].append(failure)

    return memory


def increment_signal(memory: dict, pattern_name: str, delta: int = 1) -> dict:
    """Increment or decrement signal for a pattern by name."""
    pattern = next((p for p in memory["patterns"] if p["name"] == pattern_name), None)
    if pattern:
        pattern["signal"] = max(0, min(10, pattern.get("signal", 1) + delta))
    return memory


# --- LOAD Interface ---

def get_context_for_task(memory: dict, tags: Optional[list[str]] = None) -> dict:
    """
    Select relevant patterns and failures for a task.

    If tags provided, filter to items matching any tag.
    If no tags, return all patterns and failures.

    Returns patterns sorted by signal (highest first).
    """
    def matches_tags(item):
        if not tags:
            return True
        item_tags = item.get("tags", [])
        return any(t in item_tags for t in tags)

    return {
        "patterns": sorted(
            [p for p in memory["patterns"] if matches_tags(p)],
            key=lambda p: -p.get("signal", 0)
        ),
        "failures": [f for f in memory["failures"] if matches_tags(f)],
    }


def format_for_injection(context: dict) -> str:
    """
    Format context as markdown for agent injection.

    Output format:
    ## Applicable Patterns
    - **name** (signal: N)
      When: trigger
      Do: action

    ## Known Failures
    - **name**
      Symptom: what you see
      Fix: what to do

    ## Pre-flight Checks
    - [ ] `command`
    """
    lines = []

    if context["patterns"]:
        lines.append("## Applicable Patterns\n")
        for p in context["patterns"]:
            lines.append(f"- **{p['name']}** (signal: {p.get('signal', 1)})")
            lines.append(f"  When: {p['when']}")
            lines.append(f"  Do: {p['do']}")
            lines.append("")

    if context["failures"]:
        lines.append("## Known Failures\n")
        for f in context["failures"]:
            lines.append(f"- **{f['name']}**")
            lines.append(f"  Symptom: {f['symptom']}")
            lines.append(f"  Fix: {f['fix']}")
            lines.append("")

        # Pre-flight checks from failure prevention
        preflights = [f for f in context["failures"] if f.get("prevent")]
        if preflights:
            lines.append("## Pre-flight Checks\n")
            lines.append("Before verify, run:")
            for f in preflights:
                lines.append(f"- [ ] `{f['prevent']}`")
            lines.append("")

    return "\n".join(lines)


# --- Injection Logging (for evaluation) ---

def create_injection_log(
    run_id: str,
    memory: dict,
    injected_patterns: list[str],
    injected_failures: list[str],
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
        "memory_version": memory.get("version", "2.0"),
        "delta": delta_files or [],
        "tags_matched": tags_matched or [],
        "patterns": {
            "available": [p["id"] for p in memory["patterns"]],
            "injected": injected_patterns,
            "utilized": []  # filled after run by evaluator
        },
        "failures": {
            "available": [f["id"] for f in memory["failures"]],
            "injected": injected_failures,
            "matched": []  # filled after run by evaluator
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


# --- CLI for testing ---

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python memory.py <command> [args]")
        print("Commands:")
        print("  load <path>              - Load and display memory")
        print("  context <path> [tags]    - Get context for tags")
        print("  inject <path> [tags]     - Format injection markdown")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "load":
        path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory.json")
        memory = load_memory(path)
        print(json.dumps(memory, indent=2))

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

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
