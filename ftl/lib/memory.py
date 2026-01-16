#!/usr/bin/env python3
"""Memory operations with explicit limits, pruning, and graph relationships."""

from dataclasses import dataclass, asdict, field
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import json
import argparse
import sys
import math

# Support both standalone execution and module import
try:
    from lib.embeddings import similarity as semantic_similarity
    from lib.atomicfile import atomic_json_update
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import similarity as semantic_similarity
    from atomicfile import atomic_json_update


MEMORY_FILE = Path(".ftl/memory.json")

# Pruning configuration
DEFAULT_MAX_FAILURES = 500
DEFAULT_MAX_PATTERNS = 200
DEFAULT_DECAY_HALF_LIFE_DAYS = 30  # Importance halves every 30 days
DEFAULT_MIN_IMPORTANCE_THRESHOLD = 0.1  # Entries below this get pruned


@dataclass
class Failure:
    name: str           # kebab-case slug
    trigger: str        # exact error message
    fix: str            # solution or "UNKNOWN"
    match: str          # regex for log matching
    cost: int           # tokens spent
    source: list        # workspace IDs
    # Decay and graph relationships
    access_count: int = 0       # How many times this was retrieved
    last_accessed: str = ""     # ISO timestamp of last retrieval
    related: list = field(default_factory=list)  # Names of related entries
    # Feedback tracking
    times_helped: int = 0       # Times this memory led to success
    times_failed: int = 0       # Times this memory was injected but didn't help


@dataclass
class Pattern:
    name: str           # kebab-case slug
    trigger: str        # when this applies
    insight: str        # the non-obvious thing
    saved: int          # tokens saved
    source: list        # workspace IDs
    # Decay and graph relationships
    access_count: int = 0       # How many times this was retrieved
    last_accessed: str = ""     # ISO timestamp of last retrieval
    related: list = field(default_factory=list)  # Names of related entries
    # Feedback tracking
    times_helped: int = 0       # Times this memory led to success
    times_failed: int = 0       # Times this memory was injected but didn't help


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


def _calculate_age_decay(created_at: str, half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS) -> float:
    """Calculate decay factor based on age using exponential decay.

    Returns value between 0.0 (very old) and 1.0 (just created).
    Half-life determines how fast importance decays.
    """
    if not created_at:
        return 1.0
    try:
        created = datetime.fromisoformat(created_at)
        age_days = (datetime.now() - created).days
        # Exponential decay: factor = 0.5^(age/half_life)
        return math.pow(0.5, age_days / half_life_days)
    except (ValueError, TypeError):
        return 1.0


def _calculate_effectiveness(entry: dict) -> float:
    """Calculate effectiveness factor based on feedback.

    Returns value between 0.5 (unhelpful) and 1.5 (very helpful).
    Neutral (no feedback) returns 1.0.
    """
    helped = entry.get("times_helped", 0)
    failed = entry.get("times_failed", 0)
    total = helped + failed

    if total == 0:
        return 1.0

    # Effectiveness ratio: 0.5 to 1.5 based on help/fail ratio
    ratio = helped / total
    return 0.5 + ratio  # Maps [0, 1] -> [0.5, 1.5]


def _calculate_importance(
    entry: dict,
    value_key: str = "cost",
    half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS
) -> float:
    """Calculate importance score combining value, access frequency, recency, and effectiveness.

    Importance = log₂(value + 1) × age_decay × access_boost × effectiveness

    This balances:
    - Base value (cost or saved tokens)
    - Time decay (older entries matter less)
    - Access frequency boost (frequently used entries are important)
    - Effectiveness (helpful entries persist, unhelpful decay faster)
    """
    value = entry.get(value_key, 0)
    base_score = math.log2(value + 1)

    age_decay = _calculate_age_decay(entry.get("created_at", ""), half_life_days)
    access_boost = 1 + 0.1 * entry.get("access_count", 0)
    effectiveness = _calculate_effectiveness(entry)

    return base_score * age_decay * access_boost * effectiveness


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


def prune_memory(
    path: Path = MEMORY_FILE,
    max_failures: int = DEFAULT_MAX_FAILURES,
    max_patterns: int = DEFAULT_MAX_PATTERNS,
    min_importance: float = DEFAULT_MIN_IMPORTANCE_THRESHOLD,
    half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS,
) -> dict:
    """Prune memory to remove low-importance entries and enforce size limits.

    Strategy:
    1. Calculate importance score for each entry
    2. Remove entries below min_importance threshold
    3. If still over limit, keep top entries by importance

    Returns:
        {"pruned_failures": N, "pruned_patterns": M, "remaining_failures": X, "remaining_patterns": Y}
    """
    _ensure_memory_file(path)

    def _prune(memory: dict) -> dict:
        failures = memory.get("failures", [])
        patterns = memory.get("patterns", [])

        original_failures = len(failures)
        original_patterns = len(patterns)

        # Calculate importance and filter
        scored_failures = [
            (f, _calculate_importance(f, "cost", half_life_days))
            for f in failures
        ]
        scored_patterns = [
            (p, _calculate_importance(p, "saved", half_life_days))
            for p in patterns
        ]

        # Filter by minimum importance
        scored_failures = [(f, s) for f, s in scored_failures if s >= min_importance]
        scored_patterns = [(p, s) for p, s in scored_patterns if s >= min_importance]

        # Sort by importance (highest first) and enforce limits
        scored_failures.sort(key=lambda x: x[1], reverse=True)
        scored_patterns.sort(key=lambda x: x[1], reverse=True)

        memory["failures"] = [f for f, _ in scored_failures[:max_failures]]
        memory["patterns"] = [p for p, _ in scored_patterns[:max_patterns]]

        return {
            "pruned_failures": original_failures - len(memory["failures"]),
            "pruned_patterns": original_patterns - len(memory["patterns"]),
            "remaining_failures": len(memory["failures"]),
            "remaining_patterns": len(memory["patterns"]),
        }

    return atomic_json_update(path, _prune)


def add_relationship(
    entry_name: str,
    related_name: str,
    entry_type: str = "failure",
    path: Path = MEMORY_FILE,
) -> str:
    """Add a relationship between two entries.

    Relationships are bidirectional - if A relates to B, B also relates to A.

    Args:
        entry_name: Name of the source entry
        related_name: Name of the related entry
        entry_type: "failure" or "pattern"
        path: Path to memory file

    Returns: "added" | "exists" | "not_found:{name}"
    """
    _ensure_memory_file(path)

    def _update(memory: dict) -> str:
        key = "failures" if entry_type == "failure" else "patterns"
        entries = memory.get(key, [])

        source = next((e for e in entries if e.get("name") == entry_name), None)
        target = next((e for e in entries if e.get("name") == related_name), None)

        if not source:
            return f"not_found:{entry_name}"
        if not target:
            return f"not_found:{related_name}"

        # Add bidirectional relationship
        source_related = source.setdefault("related", [])
        target_related = target.setdefault("related", [])

        if related_name in source_related:
            return "exists"

        source_related.append(related_name)
        target_related.append(entry_name)
        return "added"

    return atomic_json_update(path, _update)


def get_related_entries(
    entry_name: str,
    entry_type: str = "failure",
    max_hops: int = 2,
    path: Path = MEMORY_FILE,
) -> list:
    """Get entries related to a given entry, supporting multi-hop traversal.

    This enables pattern matching across related failures/patterns,
    similar to graph-based memory systems.

    Args:
        entry_name: Name of the starting entry
        entry_type: "failure" or "pattern"
        max_hops: Maximum relationship hops (default: 2)
        path: Path to memory file

    Returns:
        List of related entries with hop distance:
        [{"entry": {...}, "hops": 1}, {"entry": {...}, "hops": 2}, ...]
    """
    memory = load_memory(path)
    key = "failures" if entry_type == "failure" else "patterns"
    entries = {e["name"]: e for e in memory.get(key, []) if "name" in e}

    if entry_name not in entries:
        return []

    visited = {entry_name}
    result = []
    current_level = [entry_name]

    for hop in range(1, max_hops + 1):
        next_level = []
        for name in current_level:
            entry = entries.get(name, {})
            for related_name in entry.get("related", []):
                if related_name not in visited and related_name in entries:
                    visited.add(related_name)
                    next_level.append(related_name)
                    result.append({
                        "entry": entries[related_name],
                        "hops": hop
                    })
        current_level = next_level
        if not current_level:
            break

    return result


def track_access(entry_names: list, entry_type: str = "failure", path: Path = MEMORY_FILE) -> None:
    """Update access count and last_accessed timestamp for retrieved entries.

    Called automatically when entries are retrieved via get_context.
    """
    if not entry_names:
        return

    _ensure_memory_file(path)

    def _update(memory: dict) -> None:
        key = "failures" if entry_type == "failure" else "patterns"
        now = datetime.now().isoformat()

        for entry in memory.get(key, []):
            if entry.get("name") in entry_names:
                entry["access_count"] = entry.get("access_count", 0) + 1
                entry["last_accessed"] = now
        return None

    atomic_json_update(path, _update)


def record_feedback(
    entry_name: str,
    entry_type: str = "failure",
    helped: bool = True,
    path: Path = MEMORY_FILE
) -> str:
    """Record whether an injected memory was helpful.

    Args:
        entry_name: Name of the memory entry
        entry_type: "failure" or "pattern"
        helped: True if memory contributed to success, False if it didn't help
        path: Path to memory file

    Returns: "updated" | "not_found"
    """
    _ensure_memory_file(path)

    def _update(memory: dict) -> str:
        key = "failures" if entry_type == "failure" else "patterns"

        for entry in memory.get(key, []):
            if entry.get("name") == entry_name:
                if helped:
                    entry["times_helped"] = entry.get("times_helped", 0) + 1
                else:
                    entry["times_failed"] = entry.get("times_failed", 0) + 1
                return "updated"

        return "not_found"

    return atomic_json_update(path, _update)


def record_feedback_batch(
    utilized: list,
    injected: list,
    path: Path = MEMORY_FILE
) -> dict:
    """Record feedback for a batch of memories.

    Args:
        utilized: List of {"name": str, "type": "failure"|"pattern"} that helped
        injected: List of {"name": str, "type": "failure"|"pattern"} that were injected
        path: Path to memory file

    Returns: {"helped": N, "not_helped": M}
    """
    utilized_set = {(m["name"], m["type"]) for m in utilized}
    injected_set = {(m["name"], m["type"]) for m in injected}

    result = {"helped": 0, "not_helped": 0}

    for name, entry_type in injected_set:
        helped = (name, entry_type) in utilized_set
        status = record_feedback(name, entry_type, helped, path)
        if status == "updated":
            if helped:
                result["helped"] += 1
            else:
                result["not_helped"] += 1

    return result


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
            # Only set created_at if not already provided
            if "created_at" not in failure:
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
            # Only set created_at if not already provided
            if "created_at" not in pattern:
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


def get_stats(path: Path = MEMORY_FILE) -> dict:
    """Get memory statistics including age distribution and importance scores.

    Returns statistics useful for understanding memory health and deciding
    when to prune.
    """
    memory = load_memory(path)
    failures = memory.get("failures", [])
    patterns = memory.get("patterns", [])

    def calc_stats(entries: list, value_key: str) -> dict:
        if not entries:
            return {
                "count": 0, "avg_importance": 0, "avg_age_days": 0,
                "total_access_count": 0, "with_relationships": 0
            }

        importances = [_calculate_importance(e, value_key) for e in entries]
        ages = []
        for e in entries:
            created = e.get("created_at", "")
            if created:
                try:
                    age = (datetime.now() - datetime.fromisoformat(created)).days
                    ages.append(age)
                except ValueError:
                    pass

        return {
            "count": len(entries),
            "avg_importance": round(sum(importances) / len(importances), 3) if importances else 0,
            "avg_age_days": round(sum(ages) / len(ages)) if ages else 0,
            "total_access_count": sum(e.get("access_count", 0) for e in entries),
            "with_relationships": sum(1 for e in entries if e.get("related", [])),
        }

    return {
        "failures": calc_stats(failures, "cost"),
        "patterns": calc_stats(patterns, "saved"),
    }


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

    # prune command
    prune = subparsers.add_parser("prune", help="Prune low-importance entries")
    prune.add_argument("--max-failures", type=int, default=DEFAULT_MAX_FAILURES)
    prune.add_argument("--max-patterns", type=int, default=DEFAULT_MAX_PATTERNS)
    prune.add_argument("--min-importance", type=float, default=DEFAULT_MIN_IMPORTANCE_THRESHOLD)
    prune.add_argument("--half-life", type=float, default=DEFAULT_DECAY_HALF_LIFE_DAYS)

    # add-relationship command
    rel = subparsers.add_parser("add-relationship", help="Add relationship between entries")
    rel.add_argument("source", help="Source entry name")
    rel.add_argument("target", help="Target entry name")
    rel.add_argument("--type", default="failure", help="Entry type: failure or pattern")

    # related command
    related = subparsers.add_parser("related", help="Get related entries")
    related.add_argument("name", help="Entry name")
    related.add_argument("--type", default="failure", help="Entry type: failure or pattern")
    related.add_argument("--max-hops", type=int, default=2, help="Max relationship hops")

    # stats command
    stats = subparsers.add_parser("stats", help="Get memory statistics")

    # feedback command
    fb = subparsers.add_parser("feedback", help="Record feedback for a memory entry")
    fb.add_argument("name", help="Entry name")
    fb.add_argument("--type", default="failure", help="Entry type: failure or pattern")
    fb.add_argument("--helped", action="store_true", help="Memory was helpful")
    fb.add_argument("--failed", action="store_true", help="Memory didn't help")

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

    elif args.command == "prune":
        result = prune_memory(
            max_failures=args.max_failures,
            max_patterns=args.max_patterns,
            min_importance=args.min_importance,
            half_life_days=args.half_life,
        )
        print(json.dumps(result, indent=2))

    elif args.command == "add-relationship":
        result = add_relationship(args.source, args.target, args.type)
        print(result)

    elif args.command == "related":
        result = get_related_entries(args.name, args.type, args.max_hops)
        print(json.dumps(result, indent=2))

    elif args.command == "stats":
        result = get_stats()
        print(json.dumps(result, indent=2))

    elif args.command == "feedback":
        if args.helped:
            result = record_feedback(args.name, args.type, helped=True)
        elif args.failed:
            result = record_feedback(args.name, args.type, helped=False)
        else:
            print("Must specify --helped or --failed")
            sys.exit(1)
        print(result)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
