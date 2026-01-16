#!/usr/bin/env python3
"""Memory operations with explicit limits."""

from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime
import json
import argparse
import sys

# Support both standalone execution and module import
try:
    from lib.embeddings import similarity as semantic_similarity
    from lib.atomicfile import atomic_json_update
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import similarity as semantic_similarity
    from atomicfile import atomic_json_update


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


def _ensure_memory_file(path: Path = MEMORY_FILE) -> None:
    """Ensure memory file exists for atomic operations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({"failures": [], "patterns": []}, indent=2))


def is_duplicate(trigger: str, existing: list, threshold: float = 0.85) -> tuple:
    """Check if trigger is duplicate of existing entry.

    Uses semantic similarity when available (sentence-transformers),
    otherwise falls back to SequenceMatcher ratio.

    Returns: (is_duplicate: bool, existing_name: str | None)
    """
    for entry in existing:
        ratio = semantic_similarity(trigger, entry.get("trigger", ""))
        if ratio > threshold:
            return True, entry.get("name")
    return False, None


def _hybrid_score(relevance: float, value: int) -> float:
    """Compute hybrid score balancing relevance and cost/saved value.

    Score = relevance × log₂(value + 1)

    This weights both "how relevant is this?" and "how expensive/valuable?"
    """
    import math
    return relevance * math.log2(value + 1)


def _score_entries(entries: list, objective: str, value_key: str, threshold: float) -> tuple:
    """Score entries by semantic relevance and partition by threshold.

    Returns:
        (relevant_entries, fallback_entries) - both sorted appropriately
    """
    relevant = []
    fallback = []

    for entry in entries:
        trigger = entry.get("trigger", "")
        value = entry.get(value_key, 0)
        relevance = semantic_similarity(objective, trigger)

        scored_entry = {
            **entry,
            "_relevance": round(relevance, 3),
            "_score": round(_hybrid_score(relevance, value), 3),
        }

        if relevance >= threshold:
            relevant.append(scored_entry)
        else:
            fallback.append(scored_entry)

    # Sort relevant by hybrid score, fallback by raw value
    relevant.sort(key=lambda x: x["_score"], reverse=True)
    fallback.sort(key=lambda x: x.get(value_key, 0), reverse=True)

    return relevant, fallback


def get_context(
    task_type: str = "BUILD",
    tags: list = None,
    objective: str = None,
    max_failures: int = 5,
    max_patterns: int = 3,
    relevance_threshold: float = 0.25,
    min_results: int = 1,
) -> dict:
    """Get failures and patterns for injection with semantic relevance.

    When objective is provided, entries are scored by semantic similarity
    to the objective combined with their cost/saved value (hybrid scoring).
    This ensures relevant memories are prioritized while still surfacing
    expensive failures as a safety net.

    Args:
        task_type: SPEC, BUILD, or VERIFY (for future filtering)
        tags: Optional filter tags
        objective: Semantic anchor for relevance scoring (task context)
        max_failures: Maximum failures to return (default: 5)
        max_patterns: Maximum patterns to return (default: 3)
        relevance_threshold: Minimum relevance score (default: 0.25)
        min_results: Minimum results to return even if below threshold (default: 1)

    Returns:
        {"failures": [...], "patterns": [...]}
        Each entry includes _relevance and _score when objective provided.
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

    if objective:
        # Semantic retrieval with hybrid scoring
        rel_failures, fb_failures = _score_entries(
            failures, objective, "cost", relevance_threshold
        )
        rel_patterns, fb_patterns = _score_entries(
            patterns, objective, "saved", relevance_threshold
        )

        # Take from relevant first, fill from fallback if needed
        result_failures = rel_failures[:max_failures]
        if len(result_failures) < min_results and fb_failures:
            needed = min_results - len(result_failures)
            result_failures.extend(fb_failures[:needed])

        result_patterns = rel_patterns[:max_patterns]
        if len(result_patterns) < min_results and fb_patterns:
            needed = min_results - len(result_patterns)
            result_patterns.extend(fb_patterns[:needed])

        failures = result_failures[:max_failures]
        patterns = result_patterns[:max_patterns]
    else:
        # Traditional cost-based sorting (backwards compatible)
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


def add_failure(failure: dict, path: Path = MEMORY_FILE) -> str:
    """Add failure entry with deduplication using atomic file operations.

    Returns: "added" | "merged:{name}"
    """
    _ensure_memory_file(path)

    def _update(memory: dict) -> str:
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
            return f"merged:{existing_name}"
        else:
            failure["created_at"] = datetime.now().isoformat()
            memory.setdefault("failures", []).append(failure)
            return "added"

    return atomic_json_update(path, _update)


def add_pattern(pattern: dict, path: Path = MEMORY_FILE) -> str:
    """Add pattern entry with deduplication using atomic file operations.

    Returns: "added" | "duplicate:{name}"
    """
    _ensure_memory_file(path)

    def _update(memory: dict) -> str:
        existing = memory.get("patterns", [])
        is_dup, existing_name = is_duplicate(pattern.get("trigger", ""), existing)

        if is_dup:
            return f"duplicate:{existing_name}"
        else:
            pattern["created_at"] = datetime.now().isoformat()
            memory.setdefault("patterns", []).append(pattern)
            return "added"

    return atomic_json_update(path, _update)


def query(topic: str, threshold: float = 0.3) -> list:
    """Query memory for relevant entries, ranked by semantic similarity.

    Uses semantic similarity when available (sentence-transformers),
    otherwise falls back to SequenceMatcher ratio.

    Args:
        topic: Search topic
        threshold: Minimum similarity score (default: 0.3)

    Returns:
        List of matching entries sorted by similarity score (highest first)
    """
    memory = load_memory()
    results = []

    for f in memory.get("failures", []):
        score = semantic_similarity(topic, f.get("trigger", ""))
        if score > threshold:
            results.append({"type": "failure", "score": round(score, 3), **f})

    for p in memory.get("patterns", []):
        score = semantic_similarity(topic, p.get("trigger", ""))
        if score > threshold:
            results.append({"type": "pattern", "score": round(score, 3), **p})

    return sorted(results, key=lambda x: x["score"], reverse=True)


def main():
    parser = argparse.ArgumentParser(description="FTL memory operations")
    subparsers = parser.add_subparsers(dest="command")

    # context command
    ctx = subparsers.add_parser("context", help="Get context for injection")
    ctx.add_argument("--type", default="BUILD", help="Task type: SPEC, BUILD, VERIFY")
    ctx.add_argument("--tags", help="Comma-separated filter tags")
    ctx.add_argument("--objective", help="Semantic anchor for relevance scoring")
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
                task_type=args.type,
                tags=tags,
                objective=args.objective,
                max_failures=args.max_failures,
                max_patterns=args.max_patterns,
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
