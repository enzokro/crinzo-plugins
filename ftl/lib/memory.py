#!/usr/bin/env python3
"""Memory operations with fastsql database backend.

Provides failures and patterns storage with semantic similarity,
graph relationships, feedback tracking, and importance-based pruning.
"""

from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import json
import argparse
import sys
import math
import hashlib

# Support both standalone execution and module import
try:
    from lib.db import get_db, init_db, Memory, MemoryEdge
    from lib.db.embeddings import (
        embed, embed_to_blob, blob_to_embed,
        similarity as semantic_similarity,
        cosine_similarity_blob, is_available
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from db import get_db, init_db, Memory, MemoryEdge
    from db.embeddings import (
        embed, embed_to_blob, blob_to_embed,
        similarity as semantic_similarity,
        cosine_similarity_blob, is_available
    )


# Note: All storage is now in .ftl/ftl.db
# The 'path' parameters in functions below are deprecated and ignored.


# Pruning configuration
DEFAULT_MAX_FAILURES = 500
DEFAULT_MAX_PATTERNS = 200
DEFAULT_DECAY_HALF_LIFE_DAYS = 30
DEFAULT_MIN_IMPORTANCE_THRESHOLD = 0.1

# Tiered injection thresholds
TIER_CRITICAL_THRESHOLD = 0.6
TIER_PRODUCTIVE_THRESHOLD = 0.4
TIER_EXPLORATION_THRESHOLD = 0.25

# Quality gate minimums
MIN_TRIGGER_LENGTH = 10
MIN_FAILURE_COST = 100

# Valid relationship types
RELATIONSHIP_TYPES = {"co_occurs", "causes", "solves", "prerequisite", "variant"}

# Relationship weights for graph traversal
DEFAULT_RELATIONSHIP_WEIGHTS = {
    "solves": 1.5,
    "causes": 1.0,
    "prerequisite": 1.0,
    "co_occurs": 0.8,
    "variant": 0.7,
}
DEFAULT_MIN_WEIGHT_PRODUCT = 0.5


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


# =============================================================================
# Core Memory Operations
# =============================================================================

def add_failure(failure: dict, path: Path = None, validate: bool = True) -> str:
    """Add failure entry to database.

    PRESERVES EXISTING API: Takes dict, returns status string.
    The path parameter is ignored (preserved for API compatibility).

    Args:
        failure: Failure dict with name, trigger, fix, cost, etc.
        path: Ignored (database used instead)
        validate: If True, validate entry quality before adding

    Returns: "added" | "merged:{name}" | "rejected:{reason}"
    """
    # Quality gate check
    if validate:
        is_valid, reason = _validate_entry_quality(failure, "failure")
        if not is_valid:
            return f"rejected:{reason}"

    db = _ensure_db()
    memories = db.t.memory

    # Extract fields from dict
    name = failure.get("name", "")
    trigger = failure.get("trigger", "")
    fix = failure.get("fix", "")
    cost = failure.get("cost", 0)
    match_regex = failure.get("match")
    source = failure.get("source", [])
    related = failure.get("related", [])
    related_typed = failure.get("related_typed", {})
    cross_rels = failure.get("cross_relationships", {})

    # Check for duplicate by name
    existing = list(memories.rows_where("name = ? AND type = ?", [name, "failure"]))
    if existing:
        old = existing[0]
        # Merge: combine sources, keep higher cost
        old_source = json.loads(old["source"]) if old["source"] else []
        new_source = list(set(old_source + source))
        new_cost = max(old["cost"], cost)
        memories.update({"source": json.dumps(new_source), "cost": new_cost}, old["id"])
        return f"merged:{name}"

    # Check for semantic duplicate
    is_dup, existing_name = _is_duplicate(trigger, "failure", 0.85)
    if is_dup:
        # Merge with semantically similar entry
        dup_rows = list(memories.rows_where("name = ? AND type = ?", [existing_name, "failure"]))
        if dup_rows:
            old = dup_rows[0]
            old_source = json.loads(old["source"]) if old["source"] else []
            new_source = list(set(old_source + source))
            new_cost = max(old["cost"], cost)
            memories.update({"source": json.dumps(new_source), "cost": new_cost}, old["id"])
        return f"merged:{existing_name}"

    # Generate embedding
    emb = embed(trigger)
    emb_blob = embed_to_blob(emb) if emb else None

    # Compute initial importance
    importance = _calculate_importance_score(cost, 0, 0, 0)

    # Insert new entry
    now = failure.get("created_at", datetime.now().isoformat())
    memories.insert(Memory(
        name=name,
        type="failure",
        trigger=trigger,
        resolution=fix,
        match=match_regex,
        cost=cost,
        source=json.dumps(source),
        created_at=now,
        last_accessed="",
        access_count=0,
        times_helped=0,
        times_failed=0,
        importance=importance,
        related_typed=json.dumps(related_typed),
        cross_relationships=json.dumps(cross_rels),
        embedding=emb_blob
    ))

    return "added"


def add_pattern(pattern: dict, path: Path = None, validate: bool = True) -> str:
    """Add pattern entry to database.

    PRESERVES EXISTING API: Takes dict, returns status string.

    Args:
        pattern: Pattern dict with name, trigger, insight, saved, etc.
        path: Ignored (database used instead)
        validate: If True, validate entry quality before adding

    Returns: "added" | "duplicate:{name}" | "rejected:{reason}"
    """
    if validate:
        is_valid, reason = _validate_entry_quality(pattern, "pattern")
        if not is_valid:
            return f"rejected:{reason}"

    db = _ensure_db()
    memories = db.t.memory

    name = pattern.get("name", "")
    trigger = pattern.get("trigger", "")
    insight = pattern.get("insight", "")
    saved = pattern.get("saved", 0)
    source = pattern.get("source", [])
    related_typed = pattern.get("related_typed", {})
    cross_rels = pattern.get("cross_relationships", {})

    # Check for duplicate by name
    existing = list(memories.rows_where("name = ? AND type = ?", [name, "pattern"]))
    if existing:
        return f"duplicate:{name}"

    # Check for semantic duplicate
    is_dup, existing_name = _is_duplicate(trigger, "pattern", 0.85)
    if is_dup:
        return f"duplicate:{existing_name}"

    # Generate embedding
    emb = embed(trigger)
    emb_blob = embed_to_blob(emb) if emb else None

    importance = _calculate_importance_score(saved, 0, 0, 0)

    now = pattern.get("created_at", datetime.now().isoformat())
    memories.insert(Memory(
        name=name,
        type="pattern",
        trigger=trigger,
        resolution=insight,
        match=None,
        cost=saved,  # Store 'saved' in cost field for patterns
        source=json.dumps(source),
        created_at=now,
        last_accessed="",
        access_count=0,
        times_helped=0,
        times_failed=0,
        importance=importance,
        related_typed=json.dumps(related_typed),
        cross_relationships=json.dumps(cross_rels),
        embedding=emb_blob
    ))

    return "added"


def get_context(
    task_type: str = "BUILD",
    tags: list = None,
    objective: str = None,
    max_failures: int = 5,
    max_patterns: int = 3,
    relevance_threshold: float = 0.25,
    min_results: int = 1,
    expand_related: bool = False,
    track_access: bool = True,
    include_tiers: bool = False,
) -> dict:
    """Get failures and patterns for injection with semantic relevance.

    Args:
        task_type: SPEC, BUILD, or VERIFY (for future filtering)
        tags: Optional filter tags (not implemented in DB version)
        objective: Semantic anchor for relevance scoring
        max_failures: Maximum failures to return
        max_patterns: Maximum patterns to return
        relevance_threshold: Minimum relevance score
        min_results: Minimum results even if below threshold
        expand_related: If True, include related entries
        track_access: If True, update access counts
        include_tiers: If True, add _tier field

    Returns:
        {"failures": [...], "patterns": [...]}
    """
    db = _ensure_db()
    memories = db.t.memory

    # Load all memories by type
    failures = [_row_to_dict(r) for r in memories.rows_where("type = ?", ["failure"])]
    patterns = [_row_to_dict(r) for r in memories.rows_where("type = ?", ["pattern"])]

    if objective:
        # Semantic retrieval with hybrid scoring
        obj_emb = embed(objective)

        def score_entry(entry, value_key):
            trigger = entry.get("trigger", "")
            value = entry.get(value_key, 0)

            # Compute relevance via embedding similarity
            if obj_emb and entry.get("_embedding_blob"):
                relevance = cosine_similarity_blob(
                    embed_to_blob(obj_emb),
                    entry["_embedding_blob"]
                )
            else:
                relevance = semantic_similarity(objective, trigger)

            return relevance, _hybrid_score(relevance, value)

        # Score failures
        scored_failures = []
        for f in failures:
            rel, score = score_entry(f, "cost")
            f["_relevance"] = round(rel, 3)
            f["_score"] = round(score, 3)
            if include_tiers:
                f["_tier"] = _classify_tier(rel)
            scored_failures.append((f, rel, score))

        # Score patterns
        scored_patterns = []
        for p in patterns:
            rel, score = score_entry(p, "saved")
            p["_relevance"] = round(rel, 3)
            p["_score"] = round(score, 3)
            if include_tiers:
                p["_tier"] = _classify_tier(rel)
            scored_patterns.append((p, rel, score))

        # Partition by threshold and sort
        rel_failures = [(f, r, s) for f, r, s in scored_failures if r >= relevance_threshold]
        fb_failures = [(f, r, s) for f, r, s in scored_failures if r < relevance_threshold]
        rel_failures.sort(key=lambda x: -x[2])
        fb_failures.sort(key=lambda x: -x[0].get("cost", 0))

        rel_patterns = [(p, r, s) for p, r, s in scored_patterns if r >= relevance_threshold]
        fb_patterns = [(p, r, s) for p, r, s in scored_patterns if r < relevance_threshold]
        rel_patterns.sort(key=lambda x: -x[2])
        fb_patterns.sort(key=lambda x: -x[0].get("saved", 0))

        # Take from relevant first, fill from fallback
        result_failures = [f for f, _, _ in rel_failures[:max_failures]]
        if len(result_failures) < min_results:
            needed = min_results - len(result_failures)
            result_failures.extend([f for f, _, _ in fb_failures[:needed]])

        result_patterns = [p for p, _, _ in rel_patterns[:max_patterns]]
        if len(result_patterns) < min_results:
            needed = min_results - len(result_patterns)
            result_patterns.extend([p for p, _, _ in fb_patterns[:needed]])

        failures = result_failures[:max_failures]
        patterns = result_patterns[:max_patterns]
    else:
        # Traditional cost-based sorting
        failures = sorted(failures, key=lambda x: x.get("cost", 0), reverse=True)[:max_failures]
        patterns = sorted(patterns, key=lambda x: x.get("saved", 0), reverse=True)[:max_patterns]

    # Expand with related entries
    if expand_related:
        failure_names = {f.get("name") for f in failures}
        pattern_names = {p.get("name") for p in patterns}

        expanded_failures = []
        for f in failures:
            related = get_related_entries(f.get("name", ""), "failure", max_hops=1)
            for r in related:
                rel_entry = r.get("entry", {})
                if rel_entry.get("name") not in failure_names:
                    rel_entry["_expanded"] = True
                    rel_entry["_expanded_from"] = f.get("name")
                    expanded_failures.append(rel_entry)
                    failure_names.add(rel_entry.get("name"))
        failures.extend(expanded_failures[:max_failures - len(failures)])

        expanded_patterns = []
        for p in patterns:
            related = get_related_entries(p.get("name", ""), "pattern", max_hops=1)
            for r in related:
                rel_entry = r.get("entry", {})
                if rel_entry.get("name") not in pattern_names:
                    rel_entry["_expanded"] = True
                    rel_entry["_expanded_from"] = p.get("name")
                    expanded_patterns.append(rel_entry)
                    pattern_names.add(rel_entry.get("name"))
        patterns.extend(expanded_patterns[:max_patterns - len(patterns)])

    # Clean up internal fields before returning
    def clean_entry(e):
        e.pop("_embedding_blob", None)
        return e

    failures = [clean_entry(f) for f in failures]
    patterns = [clean_entry(p) for p in patterns]

    # Track access
    if track_access:
        failure_names = [f.get("name") for f in failures if f.get("name")]
        pattern_names = [p.get("name") for p in patterns if p.get("name")]
        if failure_names:
            _track_access(failure_names, "failure")
        if pattern_names:
            _track_access(pattern_names, "pattern")

    return {"failures": failures, "patterns": patterns}


def query(topic: str, threshold: float = 0.3) -> list:
    """Query memory for relevant entries, ranked by semantic similarity.

    Args:
        topic: Search topic
        threshold: Minimum similarity score

    Returns:
        List of matching entries sorted by similarity score
    """
    db = _ensure_db()
    memories = db.t.memory
    results = []

    for row in memories.rows:
        entry = _row_to_dict(row)
        entry.pop("_embedding_blob", None)  # Remove non-serializable blob
        score = semantic_similarity(topic, entry.get("trigger", ""))
        if score > threshold:
            entry["score"] = round(score, 3)
            results.append(entry)

    return sorted(results, key=lambda x: x["score"], reverse=True)


def prune_memory(
    path: Path = None,
    max_failures: int = DEFAULT_MAX_FAILURES,
    max_patterns: int = DEFAULT_MAX_PATTERNS,
    min_importance: float = DEFAULT_MIN_IMPORTANCE_THRESHOLD,
    half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS,
) -> dict:
    """Prune memory to remove low-importance entries and enforce size limits.

    Args:
        path: Ignored (database used instead)
        max_failures: Maximum failures to keep
        max_patterns: Maximum patterns to keep
        min_importance: Minimum importance threshold
        half_life_days: Half-life for age decay

    Returns:
        {"pruned_failures": N, "pruned_patterns": M, ...}
    """
    db = _ensure_db()
    memories = db.t.memory

    failures = list(memories.rows_where("type = ?", ["failure"]))
    patterns = list(memories.rows_where("type = ?", ["pattern"]))

    original_failures = len(failures)
    original_patterns = len(patterns)

    # Recalculate importance with decay
    def calc_importance(row, value_key="cost"):
        value = row[value_key] or 0
        return _calculate_importance_full(
            value,
            row.get("times_helped", 0),
            row.get("times_failed", 0),
            row.get("access_count", 0),
            row.get("created_at", ""),
            half_life_days
        )

    scored_failures = [(f, calc_importance(f, "cost")) for f in failures]
    scored_patterns = [(p, calc_importance(p, "cost")) for p in patterns]  # patterns use cost field for saved

    # Filter by minimum importance
    scored_failures = [(f, s) for f, s in scored_failures if s >= min_importance]
    scored_patterns = [(p, s) for p, s in scored_patterns if s >= min_importance]

    # Sort by importance and enforce limits
    scored_failures.sort(key=lambda x: x[1], reverse=True)
    scored_patterns.sort(key=lambda x: x[1], reverse=True)

    keep_failures = {f["id"] for f, _ in scored_failures[:max_failures]}
    keep_patterns = {p["id"] for p, _ in scored_patterns[:max_patterns]}

    # Delete entries not in keep sets
    pruned_failures = 0
    for row in failures:
        if row["id"] not in keep_failures:
            memories.delete(row["id"])
            pruned_failures += 1

    pruned_patterns = 0
    for row in patterns:
        if row["id"] not in keep_patterns:
            memories.delete(row["id"])
            pruned_patterns += 1

    return {
        "pruned_failures": pruned_failures,
        "pruned_patterns": pruned_patterns,
        "remaining_failures": len(keep_failures),
        "remaining_patterns": len(keep_patterns),
    }


# =============================================================================
# Relationship Operations
# =============================================================================

def add_relationship(
    entry_name: str,
    related_name: str,
    entry_type: str = "failure",
    relationship_type: str = "co_occurs",
    path: Path = None,
) -> str:
    """Add a typed relationship between two entries.

    Args:
        entry_name: Name of the source entry
        related_name: Name of the related entry
        entry_type: "failure" or "pattern"
        relationship_type: co_occurs|causes|solves|prerequisite|variant
        path: Ignored

    Returns: "added" | "exists" | "not_found:{name}" | "invalid_type:{type}"
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        return f"invalid_type:{relationship_type}"

    db = _ensure_db()
    memories = db.t.memory
    edges = db.t.memory_edge

    type_filter = "failure" if entry_type == "failure" else "pattern"

    source = list(memories.rows_where("name = ? AND type = ?", [entry_name, type_filter]))
    target = list(memories.rows_where("name = ? AND type = ?", [related_name, type_filter]))

    if not source:
        return f"not_found:{entry_name}"
    if not target:
        return f"not_found:{related_name}"

    source_id = source[0]["id"]
    target_id = target[0]["id"]

    # Check if edge exists
    existing = list(edges.rows_where(
        "from_id = ? AND to_id = ? AND rel_type = ?",
        [source_id, target_id, relationship_type]
    ))
    if existing:
        return "exists"

    # Add bidirectional edges
    weight = DEFAULT_RELATIONSHIP_WEIGHTS.get(relationship_type, 0.8)
    now = datetime.now().isoformat()

    edges.insert(MemoryEdge(
        from_id=source_id,
        to_id=target_id,
        rel_type=relationship_type,
        weight=weight,
        created_at=now
    ))

    inverse_type = _inverse_relationship(relationship_type)
    edges.insert(MemoryEdge(
        from_id=target_id,
        to_id=source_id,
        rel_type=inverse_type,
        weight=weight,
        created_at=now
    ))

    # Also update the JSON field for backwards compatibility
    source_row = source[0]
    source_typed = json.loads(source_row.get("related_typed") or "{}")
    if relationship_type not in source_typed:
        source_typed[relationship_type] = []
    if related_name not in source_typed[relationship_type]:
        source_typed[relationship_type].append(related_name)
    memories.update({"related_typed": json.dumps(source_typed)}, source_id)

    target_row = target[0]
    target_typed = json.loads(target_row.get("related_typed") or "{}")
    if inverse_type not in target_typed:
        target_typed[inverse_type] = []
    if entry_name not in target_typed[inverse_type]:
        target_typed[inverse_type].append(entry_name)
    memories.update({"related_typed": json.dumps(target_typed)}, target_id)

    return "added"


def get_related_entries(
    entry_name: str,
    entry_type: str = "failure",
    max_hops: int = 2,
    path: Path = None,
    weights: dict = None,
    min_weight_product: float = None,
) -> list:
    """Get entries related to a given entry via graph traversal.

    Args:
        entry_name: Name of the starting entry
        entry_type: "failure" or "pattern"
        max_hops: Maximum relationship hops
        path: Ignored
        weights: Relationship type weights
        min_weight_product: Minimum cumulative weight

    Returns:
        List of related entries with hop distance and path weight
    """
    if weights is None:
        weights = DEFAULT_RELATIONSHIP_WEIGHTS
    if min_weight_product is None:
        min_weight_product = DEFAULT_MIN_WEIGHT_PRODUCT

    db = _ensure_db()
    memories = db.t.memory
    edges = db.t.memory_edge

    type_filter = "failure" if entry_type == "failure" else "pattern"
    start = list(memories.rows_where("name = ? AND type = ?", [entry_name, type_filter]))
    if not start:
        return []

    start_id = start[0]["id"]

    # Build ID to entry mapping
    all_entries = {r["id"]: _row_to_dict(r) for r in memories.rows_where("type = ?", [type_filter])}

    visited = {start_id: 1.0}
    result = []
    current_level = [(start_id, 1.0)]

    for hop in range(1, max_hops + 1):
        next_level = []
        for node_id, current_weight in current_level:
            # Get outgoing edges
            for edge in edges.rows_where("from_id = ?", [node_id]):
                to_id = edge["to_id"]
                rel_type = edge["rel_type"]
                rel_weight = weights.get(rel_type, 0.8)
                new_weight = current_weight * rel_weight

                if new_weight < min_weight_product:
                    continue
                if to_id not in all_entries:
                    continue
                if to_id not in visited or visited[to_id] < new_weight:
                    visited[to_id] = new_weight
                    next_level.append((to_id, new_weight))
                    entry = all_entries[to_id].copy()
                    entry.pop("_embedding_blob", None)
                    result.append({
                        "entry": entry,
                        "hops": hop,
                        "weight": round(new_weight, 3),
                        "via": rel_type,
                    })

        current_level = next_level
        if not current_level:
            break

    result.sort(key=lambda x: (-x["weight"], x["hops"]))
    return result


def add_cross_relationship(
    failure_name: str,
    pattern_name: str,
    relationship_type: str = "solves",
    path: Path = None,
) -> str:
    """Link a failure to a pattern that solves it.

    Args:
        failure_name: Name of the failure entry
        pattern_name: Name of the pattern entry
        relationship_type: "solves" or "causes"
        path: Ignored

    Returns: "added" | "exists" | "not_found:{name}" | "invalid_type:{type}"
    """
    valid_cross_types = {"solves", "causes"}
    if relationship_type not in valid_cross_types:
        return f"invalid_type:{relationship_type}"

    db = _ensure_db()
    memories = db.t.memory

    failure = list(memories.rows_where("name = ? AND type = ?", [failure_name, "failure"]))
    pattern = list(memories.rows_where("name = ? AND type = ?", [pattern_name, "pattern"]))

    if not failure:
        return f"not_found:failure:{failure_name}"
    if not pattern:
        return f"not_found:pattern:{pattern_name}"

    failure_row = failure[0]
    pattern_row = pattern[0]

    # Update cross_relationships JSON field
    failure_cross = json.loads(failure_row.get("cross_relationships") or "{}")
    if relationship_type not in failure_cross:
        failure_cross[relationship_type] = []
    if pattern_name in failure_cross[relationship_type]:
        return "exists"
    failure_cross[relationship_type].append(pattern_name)
    memories.update({"cross_relationships": json.dumps(failure_cross)}, failure_row["id"])

    inverse_type = "solved_by" if relationship_type == "solves" else "caused_by"
    pattern_cross = json.loads(pattern_row.get("cross_relationships") or "{}")
    if inverse_type not in pattern_cross:
        pattern_cross[inverse_type] = []
    pattern_cross[inverse_type].append(failure_name)
    memories.update({"cross_relationships": json.dumps(pattern_cross)}, pattern_row["id"])

    return "added"


def get_solutions(failure_name: str, path: Path = None) -> list:
    """Get patterns that solve a specific failure.

    Args:
        failure_name: Name of the failure entry
        path: Ignored

    Returns:
        List of pattern dicts that solve this failure
    """
    db = _ensure_db()
    memories = db.t.memory

    failure = list(memories.rows_where("name = ? AND type = ?", [failure_name, "failure"]))
    if not failure:
        return []

    cross_rels = json.loads(failure[0].get("cross_relationships") or "{}")
    solving_names = cross_rels.get("solves", [])

    results = []
    for name in solving_names:
        patterns = list(memories.rows_where("name = ? AND type = ?", [name, "pattern"]))
        if patterns:
            entry = _row_to_dict(patterns[0])
            entry.pop("_embedding_blob", None)
            results.append(entry)

    return results


# =============================================================================
# Feedback and Access Tracking
# =============================================================================

def record_feedback(
    entry_name: str,
    entry_type: str = "failure",
    helped: bool = True,
    path: Path = None
) -> str:
    """Record whether an injected memory was helpful.

    Args:
        entry_name: Name of the memory entry
        entry_type: "failure" or "pattern"
        helped: True if memory contributed to success
        path: Ignored

    Returns: "updated" | "not_found"
    """
    db = _ensure_db()
    memories = db.t.memory

    type_filter = "failure" if entry_type == "failure" else "pattern"
    rows = list(memories.rows_where("name = ? AND type = ?", [entry_name, type_filter]))

    if not rows:
        return "not_found"

    row = rows[0]
    if helped:
        memories.update({"times_helped": (row.get("times_helped", 0) or 0) + 1}, row["id"])
    else:
        memories.update({"times_failed": (row.get("times_failed", 0) or 0) + 1}, row["id"])

    # Recalculate importance
    updated = list(memories.rows_where("id = ?", [row["id"]]))[0]
    new_importance = _calculate_importance_score(
        updated.get("cost", 0) or 0,
        updated.get("times_helped", 0) or 0,
        updated.get("times_failed", 0) or 0,
        updated.get("access_count", 0) or 0
    )
    memories.update({"importance": new_importance}, row["id"])

    return "updated"


def record_feedback_batch(
    utilized: list,
    injected: list,
    path: Path = None
) -> dict:
    """Record feedback for a batch of memories.

    Args:
        utilized: List of {"name": str, "type": "failure"|"pattern"} that helped
        injected: List of {"name": str, "type": "failure"|"pattern"} that were injected
        path: Ignored

    Returns: {"helped": N, "not_helped": M}
    """
    utilized_set = {(m["name"], m["type"]) for m in utilized}
    injected_set = {(m["name"], m["type"]) for m in injected}

    result = {"helped": 0, "not_helped": 0}

    for name, entry_type in injected_set:
        helped = (name, entry_type) in utilized_set
        status = record_feedback(name, entry_type, helped)
        if status == "updated":
            if helped:
                result["helped"] += 1
            else:
                result["not_helped"] += 1

    return result


def _track_access(entry_names: list, entry_type: str = "failure", path: Path = None) -> None:
    """Update access count and last_accessed timestamp."""
    if not entry_names:
        return

    db = _ensure_db()
    memories = db.t.memory
    now = datetime.now().isoformat()

    type_filter = "failure" if entry_type == "failure" else "pattern"
    for name in entry_names:
        rows = list(memories.rows_where("name = ? AND type = ?", [name, type_filter]))
        if rows:
            row = rows[0]
            memories.update({
                "access_count": (row.get("access_count", 0) or 0) + 1,
                "last_accessed": now
            }, row["id"])


# Public alias
track_access = _track_access


# =============================================================================
# Statistics
# =============================================================================

def get_stats(path: Path = None) -> dict:
    """Get memory statistics including age distribution and health metrics.

    Args:
        path: Ignored

    Returns:
        Statistics dict with failures and patterns breakdown
    """
    db = _ensure_db()
    memories = db.t.memory

    failures = list(memories.rows_where("type = ?", ["failure"]))
    patterns = list(memories.rows_where("type = ?", ["pattern"]))

    def calc_stats(entries: list, value_key: str) -> dict:
        if not entries:
            return {
                "count": 0, "avg_importance": 0, "avg_age_days": 0,
                "total_access_count": 0, "with_relationships": 0,
                "health": {
                    "stale_ratio": 0, "untested_ratio": 0, "orphan_count": 0,
                    "tier_distribution": {}
                }
            }

        importances = []
        ages = []
        stale_count = 0
        untested_count = 0
        orphan_count = 0
        tier_counts = {"critical": 0, "productive": 0, "exploration": 0, "archive": 0}

        now = datetime.now()
        for e in entries:
            importances.append(e.get("importance", 0) or 0)

            created = e.get("created_at", "")
            if created:
                try:
                    created_dt = datetime.fromisoformat(created)
                    age = (now - created_dt).days
                    ages.append(age)
                    if age > 90 and (e.get("access_count", 0) or 0) == 0:
                        stale_count += 1
                except ValueError:
                    pass

            if (e.get("times_helped", 0) or 0) == 0 and (e.get("times_failed", 0) or 0) == 0:
                untested_count += 1

            related_typed = json.loads(e.get("related_typed") or "{}")
            cross_rels = json.loads(e.get("cross_relationships") or "{}")
            if not related_typed and not cross_rels:
                orphan_count += 1

            access = e.get("access_count", 0) or 0
            if access >= 5:
                tier_counts["critical"] += 1
            elif access >= 2:
                tier_counts["productive"] += 1
            elif access >= 1:
                tier_counts["exploration"] += 1
            else:
                tier_counts["archive"] += 1

        n = len(entries)
        return {
            "count": n,
            "avg_importance": round(sum(importances) / len(importances), 3) if importances else 0,
            "avg_age_days": round(sum(ages) / len(ages)) if ages else 0,
            "total_access_count": sum((e.get("access_count", 0) or 0) for e in entries),
            "with_relationships": sum(1 for e in entries if json.loads(e.get("related_typed") or "{}")),
            "health": {
                "stale_ratio": round(stale_count / n, 3) if n else 0,
                "untested_ratio": round(untested_count / n, 3) if n else 0,
                "orphan_count": orphan_count,
                "tier_distribution": tier_counts,
            }
        }

    return {
        "failures": calc_stats(failures, "cost"),
        "patterns": calc_stats(patterns, "cost"),
    }


# =============================================================================
# Helper Functions
# =============================================================================

def _row_to_dict(row) -> dict:
    """Convert database row to memory dict format."""
    entry_type = row["type"]
    is_failure = entry_type == "failure"

    result = {
        "name": row["name"],
        "type": entry_type,
        "trigger": row["trigger"],
        "source": json.loads(row["source"]) if row["source"] else [],
        "access_count": row.get("access_count", 0) or 0,
        "last_accessed": row.get("last_accessed", ""),
        "times_helped": row.get("times_helped", 0) or 0,
        "times_failed": row.get("times_failed", 0) or 0,
        "importance": row.get("importance", 0) or 0,
        "created_at": row.get("created_at", ""),
        "_embedding_blob": row.get("embedding"),
    }

    if is_failure:
        result["fix"] = row["resolution"]
        result["match"] = row.get("match")
        result["cost"] = row.get("cost", 0) or 0
    else:
        result["insight"] = row["resolution"]
        result["saved"] = row.get("cost", 0) or 0  # patterns store saved in cost field

    # Include relationship data
    result["related_typed"] = json.loads(row.get("related_typed") or "{}")
    result["cross_relationships"] = json.loads(row.get("cross_relationships") or "{}")

    return result


def _is_duplicate(trigger: str, entry_type: str, threshold: float = 0.85) -> tuple:
    """Check if trigger is duplicate of existing entry."""
    if not trigger:
        return False, None

    db = _ensure_db()
    memories = db.t.memory

    existing = list(memories.rows_where("type = ?", [entry_type]))
    for row in existing:
        existing_trigger = row.get("trigger", "")
        ratio = semantic_similarity(trigger, existing_trigger)
        if ratio > threshold:
            return True, row.get("name")

    return False, None


def _validate_entry_quality(entry: dict, entry_type: str) -> tuple:
    """Validate entry meets quality gates."""
    trigger = entry.get("trigger", "")

    if len(trigger.strip()) < MIN_TRIGGER_LENGTH:
        return False, f"trigger_too_short:{len(trigger)}"

    if entry_type == "failure":
        cost = entry.get("cost", 0)
        if cost < MIN_FAILURE_COST:
            return False, f"cost_too_low:{cost}"

        generic_triggers = ["error", "failed", "exception", "unknown"]
        if trigger.strip().lower() in generic_triggers:
            return False, "trigger_too_generic"

    elif entry_type == "pattern":
        insight = entry.get("insight", "")
        if len(insight.strip()) < MIN_TRIGGER_LENGTH:
            return False, f"insight_too_short:{len(insight)}"

    return True, ""


def _calculate_importance_score(cost: int, times_helped: int, times_failed: int, access_count: int) -> float:
    """Compute importance score for ranking."""
    base = math.log2(cost + 1) if cost > 0 else 0
    help_ratio = (times_helped + 1) / (times_helped + times_failed + 2)
    access_boost = 1 + 0.05 * math.sqrt(access_count)
    return base * help_ratio * access_boost


def _calculate_importance_full(
    value: int,
    times_helped: int,
    times_failed: int,
    access_count: int,
    created_at: str,
    half_life_days: float
) -> float:
    """Calculate full importance with age decay."""
    base_score = math.log2(value + 1) if value > 0 else 0

    # Age decay
    age_decay = 1.0
    if created_at:
        try:
            created = datetime.fromisoformat(created_at)
            age_days = (datetime.now() - created).days
            age_decay = math.pow(0.5, age_days / half_life_days)
        except ValueError:
            pass

    access_boost = 1 + 0.05 * math.sqrt(access_count)
    help_ratio = (times_helped + 1) / (times_helped + times_failed + 2)

    return base_score * age_decay * access_boost * help_ratio


def _hybrid_score(relevance: float, value: int) -> float:
    """Compute hybrid score balancing relevance and value."""
    return relevance * math.log2(value + 1) if value > 0 else 0


def _classify_tier(relevance: float) -> str:
    """Classify entry into injection tier based on relevance."""
    if relevance >= TIER_CRITICAL_THRESHOLD:
        return "critical"
    elif relevance >= TIER_PRODUCTIVE_THRESHOLD:
        return "productive"
    elif relevance >= TIER_EXPLORATION_THRESHOLD:
        return "exploration"
    return "archive"


def _inverse_relationship(rel_type: str) -> str:
    """Get the inverse of a relationship type."""
    inverses = {
        "co_occurs": "co_occurs",
        "causes": "caused_by",
        "caused_by": "causes",
        "solves": "solved_by",
        "solved_by": "solves",
        "prerequisite": "depends_on",
        "depends_on": "prerequisite",
        "variant": "variant",
    }
    return inverses.get(rel_type, rel_type)


# =============================================================================
# Legacy Compatibility (load_memory/save_memory not needed but stubbed)
# =============================================================================

def load_memory(path: Path = None) -> dict:
    """Legacy: Load memory as dict (now from database)."""
    db = _ensure_db()
    memories = db.t.memory

    failures = [_row_to_dict(r) for r in memories.rows_where("type = ?", ["failure"])]
    patterns = [_row_to_dict(r) for r in memories.rows_where("type = ?", ["pattern"])]

    # Clean up internal fields
    for f in failures:
        f.pop("_embedding_blob", None)
    for p in patterns:
        p.pop("_embedding_blob", None)

    return {"failures": failures, "patterns": patterns}


def save_memory(memory: dict, path: Path = None) -> None:
    """Legacy: Save memory dict to database (for migration only)."""
    # This would be used for migration from JSON to DB
    # Not needed for normal operation
    pass


# =============================================================================
# CLI Interface
# =============================================================================

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
    ctx.add_argument("--include-tiers", action="store_true", help="Include tier classification")

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
    rel.add_argument("--rel-type", default="co_occurs", help="Relationship type")

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

    # add-cross-relationship command
    xcr = subparsers.add_parser("add-cross-relationship", help="Link failure to solving pattern")
    xcr.add_argument("failure", help="Failure name")
    xcr.add_argument("pattern", help="Pattern name")
    xcr.add_argument("--type", default="solves", help="Relationship type: solves or causes")

    # get-solutions command
    sol = subparsers.add_parser("get-solutions", help="Get patterns that solve a failure")
    sol.add_argument("failure", help="Failure name")

    args = parser.parse_args()

    if args.command == "context":
        tags = args.tags.split(",") if args.tags else None
        include_tiers = getattr(args, 'include_tiers', False)
        if args.all:
            result = get_context(max_failures=100, max_patterns=100, include_tiers=include_tiers)
        else:
            result = get_context(
                task_type=args.type,
                tags=tags,
                objective=args.objective,
                max_failures=args.max_failures,
                max_patterns=args.max_patterns,
                include_tiers=include_tiers,
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
        result = add_relationship(
            args.source, args.target, args.type,
            relationship_type=args.rel_type
        )
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

    elif args.command == "add-cross-relationship":
        result = add_cross_relationship(args.failure, args.pattern, args.type)
        print(result)

    elif args.command == "get-solutions":
        result = get_solutions(args.failure)
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
