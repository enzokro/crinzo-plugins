"""Memory layer for Helix.

9 Core Primitives:
- store: Store new memory with semantic deduplication
- recall: Semantic search ranked by relevance x effectiveness x recency
- get: Retrieve specific memory by name
- edge: Create/strengthen relationship between memories
- edges: Query relationships
- feedback: Update scores (I decide the delta)
- decay: Reduce scores on dormant memories
- prune: Remove ineffective memories
- health: System status check

P0 Additions (code-assisted judgment):
- similar_recent: Find similar memories for systemic detection
- suggest_edges: Suggest edge connections for a memory

Legacy/Utility:
- recall_by_file_patterns: Search by file patterns
- feedback_from_verification: DEPRECATED - use feedback() with explicit delta
- chunk: SOAR chunking - extract reusable pattern from success
- consolidate: Merge similar memories
"""

from .core import (
    # Core primitives
    store,
    recall,
    get,
    edge,
    edges,
    feedback,
    decay,
    prune,
    health,
    # P0 additions (code-assisted judgment)
    similar_recent,
    suggest_edges,
    # Legacy/utility
    recall_by_file_patterns,
    feedback_from_verification,
    chunk,
    consolidate,
)

__all__ = [
    "store",
    "recall",
    "get",
    "edge",
    "edges",
    "feedback",
    "decay",
    "prune",
    "health",
    "similar_recent",
    "suggest_edges",
    "recall_by_file_patterns",
    "feedback_from_verification",
    "chunk",
    "consolidate",
]
