#!/usr/bin/env python3
"""Memory operations with explicit limits."""

from dataclasses import dataclass, asdict
from pathlib import Path
from difflib import SequenceMatcher
from datetime import datetime
import json
import argparse
import sys


MEMORY_FILE = Path(".ftl/memory.json")


@dataclass
class Failure:
    name: str           # kebab-case slug
    trigger: str        # exact error message
    fix: str            # solution or "UNKNOWN"
    match: str          # regex for log matching
    cost: int           # tokens spent
    source: list        # workspace IDs


@dataclass
class Pattern:
    name: str           # kebab-case slug
    trigger: str        # when this applies
    insight: str        # the non-obvious thing
    saved: int          # tokens saved
    source: list        # workspace IDs


def load_memory(path: Path = MEMORY_FILE) -> dict:
    """Load memory from disk."""
    if not path.exists():
        return {"failures": [], "patterns": []}
    return json.loads(path.read_text())


def save_memory(memory: dict, path: Path = MEMORY_FILE) -> None:
    """Save memory to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(memory, indent=2))


def is_duplicate(trigger: str, existing: list, threshold: float = 0.85) -> tuple:
    """Check if trigger is duplicate of existing entry.

    Returns: (is_duplicate: bool, existing_name: str | None)
    """
    for entry in existing:
        ratio = SequenceMatcher(
            None,
            trigger.lower(),
            entry.get("trigger", "").lower()
        ).ratio()
        if ratio > threshold:
            return True, entry.get("name")
    return False, None


def get_context(
    task_type: str = "BUILD",
    tags: list = None,
    max_failures: int = 5,
    max_patterns: int = 3,
) -> dict:
    """Get failures and patterns for injection.

    Args:
        task_type: SPEC, BUILD, or VERIFY (for future filtering)
        tags: Optional filter tags
        max_failures: Maximum failures to return (default: 5)
        max_patterns: Maximum patterns to return (default: 3)

    Returns:
        {"failures": [...], "patterns": [...]}
    """
    memory = load_memory()

    failures = memory.get("failures", [])
    patterns = memory.get("patterns", [])

    # Filter by tags if provided
    if tags:
        failures = [
            f for f in failures
            if any(t in f.get("tags", []) for t in tags)
        ]
        patterns = [
            p for p in patterns
            if any(t in p.get("tags", []) for t in tags)
        ]

    # Sort by cost/saved (most valuable first) and limit
    failures = sorted(
        failures,
        key=lambda x: x.get("cost", 0),
        reverse=True
    )[:max_failures]

    patterns = sorted(
        patterns,
        key=lambda x: x.get("saved", 0),
        reverse=True
    )[:max_patterns]

    return {"failures": failures, "patterns": patterns}


def add_failure(failure: dict) -> str:
    """Add failure entry with deduplication.

    Returns: "added" | "merged:{name}"
    """
    memory = load_memory()
    existing = memory.get("failures", [])

    is_dup, existing_name = is_duplicate(failure.get("trigger", ""), existing)

    if is_dup:
        # Merge: combine sources, keep higher cost
        for f in existing:
            if f.get("name") == existing_name:
                f["source"] = list(set(
                    f.get("source", []) + failure.get("source", [])
                ))
                f["cost"] = max(f.get("cost", 0), failure.get("cost", 0))
                break
        save_memory(memory)
        return f"merged:{existing_name}"
    else:
        failure["created_at"] = datetime.now().isoformat()
        memory.setdefault("failures", []).append(failure)
        save_memory(memory)
        return "added"


def add_pattern(pattern: dict) -> str:
    """Add pattern entry with deduplication.

    Returns: "added" | "duplicate:{name}"
    """
    memory = load_memory()
    existing = memory.get("patterns", [])

    is_dup, existing_name = is_duplicate(pattern.get("trigger", ""), existing)

    if is_dup:
        return f"duplicate:{existing_name}"
    else:
        pattern["created_at"] = datetime.now().isoformat()
        memory.setdefault("patterns", []).append(pattern)
        save_memory(memory)
        return "added"


def query(topic: str) -> list:
    """Query memory for relevant entries."""
    memory = load_memory()
    results = []
    topic_lower = topic.lower()

    for f in memory.get("failures", []):
        if (topic_lower in f.get("trigger", "").lower() or
            topic_lower in f.get("name", "").lower()):
            results.append({"type": "failure", **f})

    for p in memory.get("patterns", []):
        if (topic_lower in p.get("trigger", "").lower() or
            topic_lower in p.get("name", "").lower()):
            results.append({"type": "pattern", **p})

    return results


def main():
    parser = argparse.ArgumentParser(description="FTL memory operations")
    subparsers = parser.add_subparsers(dest="command")

    # context command
    ctx = subparsers.add_parser("context", help="Get context for injection")
    ctx.add_argument("--type", default="BUILD", help="Task type: SPEC, BUILD, VERIFY")
    ctx.add_argument("--tags", help="Comma-separated filter tags")
    ctx.add_argument("--max-failures", type=int, default=5)
    ctx.add_argument("--max-patterns", type=int, default=3)
    ctx.add_argument("--all", action="store_true", help="Return all entries")

    # add-failure command
    af = subparsers.add_parser("add-failure", help="Add a failure entry")
    af.add_argument("--json", required=True, help="JSON failure object")

    # add-pattern command
    ap = subparsers.add_parser("add-pattern", help="Add a pattern entry")
    ap.add_argument("--json", required=True, help="JSON pattern object")

    # query command
    q = subparsers.add_parser("query", help="Query memory")
    q.add_argument("topic", help="Topic to search for")

    args = parser.parse_args()

    if args.command == "context":
        tags = args.tags.split(",") if args.tags else None
        if args.all:
            result = get_context(max_failures=100, max_patterns=100)
        else:
            result = get_context(
                args.type,
                tags,
                args.max_failures,
                args.max_patterns
            )
        print(json.dumps(result, indent=2))

    elif args.command == "add-failure":
        failure = json.loads(args.json)
        result = add_failure(failure)
        print(result)

    elif args.command == "add-pattern":
        pattern = json.loads(args.json)
        result = add_pattern(pattern)
        print(result)

    elif args.command == "query":
        results = query(args.topic)
        print(json.dumps(results, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
