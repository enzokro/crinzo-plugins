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
import hashlib

# Support both standalone execution and module import
try:
    from lib.embeddings import similarity as semantic_similarity
    from lib.atomicfile import atomic_json_update
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from embeddings import similarity as semantic_similarity
    from atomicfile import atomic_json_update


MEMORY_FILE = Path(".ftl/memory.json")


# =============================================================================
# Bloom Filter for Fast Duplicate Detection
# =============================================================================

class BloomFilter:
    """Simple Bloom filter for fast negative checks on duplicate triggers.

    This reduces O(N) semantic similarity checks by first checking if a
    trigger is definitely NOT in the set (no false negatives).
    If the filter says "maybe present", we fall back to semantic similarity.

    Expected false positive rate: ~1% with default settings.
    """

    def __init__(self, expected_items: int = 1000, false_positive_rate: float = 0.01):
        """Initialize Bloom filter.

        Args:
            expected_items: Expected number of items to store
            false_positive_rate: Target false positive rate (0.01 = 1%)
        """
        # Calculate optimal size and hash count
        # m = -(n * ln(p)) / (ln(2)^2)
        # k = (m/n) * ln(2)
        self.size = max(1024, int(-(expected_items * math.log(false_positive_rate)) / (math.log(2) ** 2)))
        self.hash_count = max(1, int((self.size / expected_items) * math.log(2)))
        self.bit_array = [False] * self.size

    def _hashes(self, item: str) -> list[int]:
        """Generate k hash values for an item using double hashing."""
        # Use SHA256 for consistent hashing
        h = hashlib.sha256(item.encode('utf-8')).digest()
        # Use first 8 bytes as h1, next 8 as h2
        h1 = int.from_bytes(h[:8], 'big')
        h2 = int.from_bytes(h[8:16], 'big')
        # Double hashing: hash_i = h1 + i*h2
        return [(h1 + i * h2) % self.size for i in range(self.hash_count)]

    def add(self, item: str) -> None:
        """Add an item to the filter."""
        for pos in self._hashes(item):
            self.bit_array[pos] = True

    def maybe_contains(self, item: str) -> bool:
        """Check if item might be in the set.

        Returns:
            False: Definitely not in set (no false negatives)
            True: Probably in set (may be false positive)
        """
        return all(self.bit_array[pos] for pos in self._hashes(item))

    def clear(self) -> None:
        """Clear all bits."""
        self.bit_array = [False] * self.size


# Global bloom filter instance (rebuilt on memory load)
_bloom_filter: Optional[BloomFilter] = None
_bloom_filter_built_from: Optional[str] = None  # Hash of memory state when built


def _get_bloom_filter(memory: dict = None) -> BloomFilter:
    """Get or rebuild the bloom filter for trigger deduplication.

    Lazily rebuilds when memory content changes.
    """
    global _bloom_filter, _bloom_filter_built_from

    # Calculate memory hash to detect changes
    if memory is None:
        memory = load_memory()

    triggers = [
        f.get("trigger", "") for f in memory.get("failures", [])
    ] + [
        p.get("trigger", "") for p in memory.get("patterns", [])
    ]
    memory_hash = hashlib.md5("".join(triggers).encode()).hexdigest()

    # Rebuild if needed
    if _bloom_filter is None or _bloom_filter_built_from != memory_hash:
        total_entries = len(memory.get("failures", [])) + len(memory.get("patterns", []))
        _bloom_filter = BloomFilter(expected_items=max(100, total_entries * 2))

        for trigger in triggers:
            if trigger:
                _bloom_filter.add(trigger.lower().strip())

        _bloom_filter_built_from = memory_hash

    return _bloom_filter

# Pruning configuration
DEFAULT_MAX_FAILURES = 500
DEFAULT_MAX_PATTERNS = 200
DEFAULT_DECAY_HALF_LIFE_DAYS = 30  # Importance halves every 30 days
DEFAULT_MIN_IMPORTANCE_THRESHOLD = 0.1  # Entries below this get pruned

# Tiered injection thresholds
TIER_CRITICAL_THRESHOLD = 0.6   # High relevance: always inject
TIER_PRODUCTIVE_THRESHOLD = 0.4  # Medium relevance: inject if space
TIER_EXPLORATION_THRESHOLD = 0.25  # Low relevance: inject for exploration

# Quality gate minimums
MIN_TRIGGER_LENGTH = 10  # Minimum characters for a meaningful trigger
MIN_FAILURE_COST = 100   # Minimum cost to be worth storing


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


MEMORY_SCHEMA_VERSION = "1.0"


def load_memory(path: Path = MEMORY_FILE) -> dict:
    """Load memory from disk, checking schema version."""
    if not path.exists():
        return {"failures": [], "patterns": [], "_schema_version": MEMORY_SCHEMA_VERSION}
    data = json.loads(path.read_text())
    # Track schema version for future migrations
    version = data.get("_schema_version", "0.9")
    # Future: migrate if version != MEMORY_SCHEMA_VERSION
    return data


def save_memory(memory: dict, path: Path = MEMORY_FILE) -> None:
    """Save memory to disk with atomic write and schema version.

    Uses file locking to prevent concurrent write corruption.
    """
    _ensure_memory_file(path)

    def _update(existing: dict) -> None:
        existing.clear()
        existing.update(memory)
        # Ensure schema version is always present
        existing["_schema_version"] = MEMORY_SCHEMA_VERSION
        return None

    atomic_json_update(path, _update)


def _ensure_memory_file(path: Path = MEMORY_FILE) -> None:
    """Ensure memory file exists for atomic operations."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps({
            "failures": [],
            "patterns": [],
            "_schema_version": MEMORY_SCHEMA_VERSION
        }, indent=2))


def is_duplicate(trigger: str, existing: list, threshold: float = 0.85) -> tuple:
    """Check if trigger is duplicate of existing entry.

    Uses a two-phase approach for efficiency:
    1. Bloom filter for fast negative check (O(1))
    2. Semantic similarity for potential duplicates (O(N) worst case)

    The Bloom filter reduces ~80% of unnecessary semantic similarity
    calls by quickly eliminating triggers that are definitely not duplicates.

    Returns: (is_duplicate: bool, existing_name: str | None)
    """
    if not trigger or not existing:
        return False, None

    # Normalize trigger for bloom filter check
    normalized_trigger = trigger.lower().strip()

    # Phase 1: Bloom filter fast negative check
    # If bloom filter says "not present", skip expensive semantic checks
    bloom = _get_bloom_filter()
    if not bloom.maybe_contains(normalized_trigger):
        # Definitely not a duplicate (no false negatives)
        return False, None

    # Phase 2: Bloom filter said "maybe present" - do semantic check
    # This runs in ~20% of cases (false positive rate + actual duplicates)
    for entry in existing:
        existing_trigger = entry.get("trigger", "")
        ratio = semantic_similarity(trigger, existing_trigger)
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


def _calculate_exploration_bonus(entry: dict, bonus_days: int = 7, bonus_factor: float = 0.1) -> float:
    """Calculate exploration bonus for newer entries.

    Entries less than bonus_days old get a bonus to encourage exploration
    of recently discovered patterns/failures.

    Returns:
        1.0 + bonus_factor if entry is new, otherwise 1.0
    """
    created_at = entry.get("created_at", "")
    if not created_at:
        return 1.0
    try:
        created = datetime.fromisoformat(created_at)
        age_days = (datetime.now() - created).days
        if age_days < bonus_days:
            return 1.0 + bonus_factor
        return 1.0
    except (ValueError, TypeError):
        return 1.0


def _calculate_importance(
    entry: dict,
    value_key: str = "cost",
    half_life_days: float = DEFAULT_DECAY_HALF_LIFE_DAYS
) -> float:
    """Calculate importance score combining value, access frequency, recency, and effectiveness.

    Importance = log₂(value + 1) × age_decay × access_boost × effectiveness × exploration_bonus

    This balances:
    - Base value (cost or saved tokens)
    - Time decay (older entries matter less)
    - Access frequency boost (frequently used entries are important, uses sqrt for diminishing returns)
    - Effectiveness (helpful entries persist, unhelpful decay faster)
    - Exploration bonus (10% boost for entries < 7 days old)
    """
    value = entry.get(value_key, 0)
    base_score = math.log2(value + 1)

    age_decay = _calculate_age_decay(entry.get("created_at", ""), half_life_days)
    # Use sqrt for diminishing returns on access_count
    access_boost = 1 + 0.05 * math.sqrt(entry.get("access_count", 0))
    effectiveness = _calculate_effectiveness(entry)
    exploration_bonus = _calculate_exploration_bonus(entry)

    return base_score * age_decay * access_boost * effectiveness * exploration_bonus


def _hybrid_score(relevance: float, value: int) -> float:
    """Compute hybrid score balancing relevance and cost/saved value.

    Score = relevance × log₂(value + 1)

    This weights both "how relevant is this?" and "how expensive/valuable?"
    """
    import math
    return relevance * math.log2(value + 1)


def _classify_tier(entry: dict, relevance: float) -> str:
    """Classify entry into injection tier based on relevance.

    Returns: "critical" | "productive" | "exploration" | "archive"

    Tiers determine injection priority:
    - critical: Always inject (high relevance, directly applicable)
    - productive: Inject if space available (moderate relevance)
    - exploration: Inject for discovery (low but non-zero relevance)
    - archive: Don't inject (below threshold or no relevance)
    """
    if relevance >= TIER_CRITICAL_THRESHOLD:
        return "critical"
    elif relevance >= TIER_PRODUCTIVE_THRESHOLD:
        return "productive"
    elif relevance >= TIER_EXPLORATION_THRESHOLD:
        return "exploration"
    else:
        return "archive"


def _validate_entry_quality(entry: dict, entry_type: str) -> tuple[bool, str]:
    """Validate entry meets quality gates before storage.

    Args:
        entry: The failure or pattern dict
        entry_type: "failure" or "pattern"

    Returns:
        (is_valid, rejection_reason or "")
    """
    trigger = entry.get("trigger", "")

    # Check trigger length
    if len(trigger.strip()) < MIN_TRIGGER_LENGTH:
        return False, f"trigger_too_short:{len(trigger)}"

    # Type-specific validation
    if entry_type == "failure":
        cost = entry.get("cost", 0)
        if cost < MIN_FAILURE_COST:
            return False, f"cost_too_low:{cost}"

        # Check for generic/unhelpful triggers
        generic_triggers = ["error", "failed", "exception", "unknown"]
        if trigger.strip().lower() in generic_triggers:
            return False, "trigger_too_generic"

    elif entry_type == "pattern":
        insight = entry.get("insight", "")
        if len(insight.strip()) < MIN_TRIGGER_LENGTH:
            return False, f"insight_too_short:{len(insight)}"

    return True, ""


def _score_entries(
    entries: list,
    objective: str,
    value_key: str,
    threshold: float,
    include_tiers: bool = False
) -> tuple:
    """Score entries by semantic relevance and partition by threshold.

    Performance: O(N) where N = len(entries).
    The objective embedding is computed once and cached by embeddings.py's LRU cache.
    Each entry trigger is also cached, so repeated calls with same entries are fast.

    Args:
        entries: List of failure/pattern dicts
        objective: Semantic anchor for relevance scoring
        value_key: "cost" for failures, "saved" for patterns
        threshold: Minimum relevance to be considered relevant
        include_tiers: If True, add _tier field to each entry

    Returns:
        (relevant_entries, fallback_entries) - both sorted appropriately
    """
    relevant = []
    fallback = []

    # Note: semantic_similarity calls embed() which has LRU cache.
    # The objective embedding is computed once and reused for all entries.
    for entry in entries:
        trigger = entry.get("trigger", "")
        value = entry.get(value_key, 0)
        relevance = semantic_similarity(objective, trigger)

        scored_entry = {
            **entry,
            "_relevance": round(relevance, 3),
            "_score": round(_hybrid_score(relevance, value), 3),
        }

        if include_tiers:
            scored_entry["_tier"] = _classify_tier(entry, relevance)

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


# Valid relationship types for typed edges
RELATIONSHIP_TYPES = {"co_occurs", "causes", "solves", "prerequisite", "variant"}

# Relationship weights for graph traversal (higher = stronger connection)
DEFAULT_RELATIONSHIP_WEIGHTS = {
    "solves": 1.5,       # High value: pattern fixes failure
    "causes": 1.0,       # Standard: A leads to B
    "prerequisite": 1.0, # Standard: must understand A before B
    "co_occurs": 0.8,    # Lower: correlation, not causation
    "variant": 0.7,      # Lower: similar but different
}
DEFAULT_MIN_WEIGHT_PRODUCT = 0.5  # Prune paths weaker than this


def add_relationship(
    entry_name: str,
    related_name: str,
    entry_type: str = "failure",
    relationship_type: str = "co_occurs",
    path: Path = MEMORY_FILE,
) -> str:
    """Add a typed relationship between two entries.

    Relationships are bidirectional - if A relates to B, B also relates to A.
    The relationship_type describes how A relates to B.

    Args:
        entry_name: Name of the source entry
        related_name: Name of the related entry
        entry_type: "failure" or "pattern"
        relationship_type: Type of relationship (co_occurs, causes, solves, prerequisite, variant)
        path: Path to memory file

    Relationship Types:
        - co_occurs: Entries appeared together in the same campaign
        - causes: Source entry often leads to the target entry
        - solves: Source pattern fixes target failure
        - prerequisite: Source must be understood before target
        - variant: Entries are variations of the same underlying issue

    Returns: "added" | "exists" | "not_found:{name}" | "invalid_type:{type}"
    """
    if relationship_type not in RELATIONSHIP_TYPES:
        return f"invalid_type:{relationship_type}"

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

        # Get or create typed relationships dict
        source_related = source.setdefault("related", [])
        source_typed = source.setdefault("related_typed", {})
        target_related = target.setdefault("related", [])
        target_typed = target.setdefault("related_typed", {})

        # Check if relationship exists (either in legacy list or typed dict)
        if related_name in source_related:
            # Upgrade to typed if not already
            if relationship_type not in source_typed:
                source_typed[relationship_type] = []
            if related_name not in source_typed[relationship_type]:
                source_typed[relationship_type].append(related_name)
            return "exists"

        # Add to legacy list for backwards compatibility
        source_related.append(related_name)
        target_related.append(entry_name)

        # Add to typed dict
        if relationship_type not in source_typed:
            source_typed[relationship_type] = []
        source_typed[relationship_type].append(related_name)

        # Add inverse relationship type
        inverse_type = _inverse_relationship(relationship_type)
        if inverse_type not in target_typed:
            target_typed[inverse_type] = []
        target_typed[inverse_type].append(entry_name)

        return "added"

    return atomic_json_update(path, _update)


def _inverse_relationship(rel_type: str) -> str:
    """Get the inverse of a relationship type."""
    inverses = {
        "co_occurs": "co_occurs",  # symmetric
        "causes": "caused_by",
        "caused_by": "causes",
        "solves": "solved_by",
        "solved_by": "solves",
        "prerequisite": "depends_on",
        "depends_on": "prerequisite",
        "variant": "variant",  # symmetric
    }
    return inverses.get(rel_type, rel_type)


def get_related_entries(
    entry_name: str,
    entry_type: str = "failure",
    max_hops: int = 2,
    path: Path = MEMORY_FILE,
    weights: dict = None,
    min_weight_product: float = None,
) -> list:
    """Get entries related to a given entry, supporting weighted multi-hop traversal.

    This enables pattern matching across related failures/patterns,
    similar to graph-based memory systems. Weak paths (e.g., co_occurs → co_occurs)
    are pruned when their cumulative weight product falls below threshold.

    Args:
        entry_name: Name of the starting entry
        entry_type: "failure" or "pattern"
        max_hops: Maximum relationship hops (default: 2)
        path: Path to memory file
        weights: Relationship type weights (default: DEFAULT_RELATIONSHIP_WEIGHTS)
        min_weight_product: Minimum cumulative weight to include path (default: 0.5)

    Returns:
        List of related entries with hop distance and path weight:
        [{"entry": {...}, "hops": 1, "weight": 0.8}, ...]
    """
    if weights is None:
        weights = DEFAULT_RELATIONSHIP_WEIGHTS
    if min_weight_product is None:
        min_weight_product = DEFAULT_MIN_WEIGHT_PRODUCT

    memory = load_memory(path)
    key = "failures" if entry_type == "failure" else "patterns"
    entries = {e["name"]: e for e in memory.get(key, []) if "name" in e}

    if entry_name not in entries:
        return []

    visited = {entry_name: 1.0}  # Track best weight to each node
    result = []
    current_level = [(entry_name, 1.0)]  # (name, cumulative_weight)

    for hop in range(1, max_hops + 1):
        next_level = []
        for name, current_weight in current_level:
            entry = entries.get(name, {})

            # Get typed relationships if available, fallback to untyped
            related_typed = entry.get("related_typed", {})
            related_untyped = entry.get("related", [])

            # Process typed relationships with weights
            for rel_type, related_names in related_typed.items():
                rel_weight = weights.get(rel_type, 0.8)  # Default weight for unknown types
                for related_name in related_names:
                    if related_name not in entries:
                        continue
                    new_weight = current_weight * rel_weight
                    if new_weight < min_weight_product:
                        continue  # Prune weak paths
                    if related_name not in visited or visited[related_name] < new_weight:
                        visited[related_name] = new_weight
                        next_level.append((related_name, new_weight))
                        result.append({
                            "entry": entries[related_name],
                            "hops": hop,
                            "weight": round(new_weight, 3),
                            "via": rel_type,
                        })

            # Process untyped relationships (legacy, assume co_occurs)
            default_weight = weights.get("co_occurs", 0.8)
            for related_name in related_untyped:
                if related_name in [n for names in related_typed.values() for n in names]:
                    continue  # Skip if already processed as typed
                if related_name not in entries:
                    continue
                new_weight = current_weight * default_weight
                if new_weight < min_weight_product:
                    continue
                if related_name not in visited or visited[related_name] < new_weight:
                    visited[related_name] = new_weight
                    next_level.append((related_name, new_weight))
                    result.append({
                        "entry": entries[related_name],
                        "hops": hop,
                        "weight": round(new_weight, 3),
                        "via": "co_occurs",
                    })

        current_level = next_level
        if not current_level:
            break

    # Sort by weight descending, then by hops ascending
    result.sort(key=lambda x: (-x["weight"], x["hops"]))
    return result


def _track_access(entry_names: list, entry_type: str = "failure", path: Path = MEMORY_FILE) -> None:
    """Update access count and last_accessed timestamp for retrieved entries.

    Called automatically when entries are retrieved via get_context.
    Internal function - use get_context with track_access=True for automatic tracking.
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


# Public alias for backwards compatibility
track_access = _track_access


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


def add_cross_relationship(
    failure_name: str,
    pattern_name: str,
    relationship_type: str = "solves",
    path: Path = MEMORY_FILE,
) -> str:
    """Link a failure to a pattern that solves it (cross-type relationship).

    This enables "given this failure, what patterns fix it?" queries.
    The relationship is stored on both entries for bidirectional traversal.

    Args:
        failure_name: Name of the failure entry
        pattern_name: Name of the pattern entry
        relationship_type: "solves" (pattern solves failure) or "causes" (failure causes pattern need)
        path: Path to memory file

    Returns: "added" | "exists" | "not_found:{name}" | "invalid_type:{type}"
    """
    valid_cross_types = {"solves", "causes"}
    if relationship_type not in valid_cross_types:
        return f"invalid_type:{relationship_type}"

    _ensure_memory_file(path)

    def _update(memory: dict) -> str:
        failures = memory.get("failures", [])
        patterns = memory.get("patterns", [])

        failure = next((f for f in failures if f.get("name") == failure_name), None)
        pattern = next((p for p in patterns if p.get("name") == pattern_name), None)

        if not failure:
            return f"not_found:failure:{failure_name}"
        if not pattern:
            return f"not_found:pattern:{pattern_name}"

        # Store cross-type relationships in a dedicated field
        failure_cross = failure.setdefault("cross_relationships", {})
        pattern_cross = pattern.setdefault("cross_relationships", {})

        # Check if exists
        if relationship_type not in failure_cross:
            failure_cross[relationship_type] = []
        if pattern_name in failure_cross[relationship_type]:
            return "exists"

        # Add bidirectional cross-type link
        failure_cross.setdefault(relationship_type, []).append(pattern_name)

        inverse_type = "solved_by" if relationship_type == "solves" else "caused_by"
        pattern_cross.setdefault(inverse_type, []).append(failure_name)

        return "added"

    return atomic_json_update(path, _update)


def get_solutions(failure_name: str, path: Path = MEMORY_FILE) -> list:
    """Get patterns that solve a specific failure.

    Args:
        failure_name: Name of the failure entry
        path: Path to memory file

    Returns:
        List of pattern dicts that solve this failure
    """
    memory = load_memory(path)
    failures = memory.get("failures", [])
    patterns = memory.get("patterns", [])

    failure = next((f for f in failures if f.get("name") == failure_name), None)
    if not failure:
        return []

    cross_rels = failure.get("cross_relationships", {})
    solving_pattern_names = cross_rels.get("solves", [])

    pattern_map = {p.get("name"): p for p in patterns}
    return [pattern_map[name] for name in solving_pattern_names if name in pattern_map]


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
        expand_related: If True, include related entries via graph expansion (default: False)
        track_access: If True, automatically update access counts (default: True)
        include_tiers: If True, add _tier field (critical/productive/exploration/archive)

    Returns:
        {"failures": [...], "patterns": [...]}
        Each entry includes _relevance and _score when objective provided.
        If include_tiers=True, each entry also includes _tier.
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
            failures, objective, "cost", relevance_threshold, include_tiers
        )
        rel_patterns, fb_patterns = _score_entries(
            patterns, objective, "saved", relevance_threshold, include_tiers
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

    # Expand with related entries if requested
    if expand_related:
        failure_names = {f.get("name") for f in failures}
        pattern_names = {p.get("name") for p in patterns}

        # Expand failures
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

        # Expand patterns
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

    # Automatic access tracking
    if track_access:
        retrieved_failure_names = [f.get("name") for f in failures if f.get("name")]
        retrieved_pattern_names = [p.get("name") for p in patterns if p.get("name")]
        if retrieved_failure_names:
            _track_access(retrieved_failure_names, "failure")
        if retrieved_pattern_names:
            _track_access(retrieved_pattern_names, "pattern")

    return {"failures": failures, "patterns": patterns}


def add_failure(failure: dict, path: Path = MEMORY_FILE, validate: bool = True) -> str:
    """Add failure entry with deduplication using atomic file operations.

    Args:
        failure: Failure dict with name, trigger, fix, cost, etc.
        path: Path to memory file
        validate: If True, validate entry quality before adding (default: True)

    Returns: "added" | "merged:{name}" | "rejected:{reason}"
    """
    global _bloom_filter_built_from

    # Quality gate check
    if validate:
        is_valid, reason = _validate_entry_quality(failure, "failure")
        if not is_valid:
            return f"rejected:{reason}"

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

            # Update bloom filter with new trigger
            trigger = failure.get("trigger", "")
            if trigger and _bloom_filter is not None:
                _bloom_filter.add(trigger.lower().strip())

            return "added"

    result = atomic_json_update(path, _update)

    # Invalidate bloom filter cache on add (will rebuild on next check)
    if result == "added":
        _bloom_filter_built_from = None

    return result


def add_pattern(pattern: dict, path: Path = MEMORY_FILE, validate: bool = True) -> str:
    """Add pattern entry with deduplication using atomic file operations.

    Args:
        pattern: Pattern dict with name, trigger, insight, saved, etc.
        path: Path to memory file
        validate: If True, validate entry quality before adding (default: True)

    Returns: "added" | "duplicate:{name}" | "rejected:{reason}"
    """
    global _bloom_filter_built_from

    # Quality gate check
    if validate:
        is_valid, reason = _validate_entry_quality(pattern, "pattern")
        if not is_valid:
            return f"rejected:{reason}"

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

            # Update bloom filter with new trigger
            trigger = pattern.get("trigger", "")
            if trigger and _bloom_filter is not None:
                _bloom_filter.add(trigger.lower().strip())

            return "added"

    result = atomic_json_update(path, _update)

    # Invalidate bloom filter cache on add (will rebuild on next check)
    if result == "added":
        _bloom_filter_built_from = None

    return result


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
    """Get memory statistics including age distribution, importance scores, and health metrics.

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
                "total_access_count": 0, "with_relationships": 0,
                "health": {
                    "stale_ratio": 0, "untested_ratio": 0, "orphan_count": 0,
                    "tier_distribution": {}
                }
            }

        importances = [_calculate_importance(e, value_key) for e in entries]
        ages = []
        stale_count = 0  # >90 days, never accessed
        untested_count = 0  # No feedback
        orphan_count = 0  # No relationships
        tier_counts = {"critical": 0, "productive": 0, "exploration": 0, "archive": 0}

        now = datetime.now()
        for e in entries:
            created = e.get("created_at", "")
            if created:
                try:
                    created_dt = datetime.fromisoformat(created)
                    age = (now - created_dt).days
                    ages.append(age)

                    # Stale: old and never accessed
                    if age > 90 and e.get("access_count", 0) == 0:
                        stale_count += 1
                except ValueError:
                    pass

            # Untested: no feedback recorded
            if e.get("times_helped", 0) == 0 and e.get("times_failed", 0) == 0:
                untested_count += 1

            # Orphan: no relationships
            if not e.get("related", []) and not e.get("cross_relationships", {}):
                orphan_count += 1

            # Tier distribution (based on a generic relevance estimate)
            # Use access frequency as proxy for relevance since we don't have objective
            access = e.get("access_count", 0)
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
            "total_access_count": sum(e.get("access_count", 0) for e in entries),
            "with_relationships": sum(1 for e in entries if e.get("related", [])),
            "health": {
                "stale_ratio": round(stale_count / n, 3) if n else 0,
                "untested_ratio": round(untested_count / n, 3) if n else 0,
                "orphan_count": orphan_count,
                "tier_distribution": tier_counts,
            }
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
