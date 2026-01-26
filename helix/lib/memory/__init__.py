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

Code-Assisted (surfaces facts, orchestrator decides):
- similar_recent: Find similar memories for systemic detection
- suggest_edges: Suggest edge connections for a memory

Utility:
- recall_by_file_patterns: Search by file patterns
- chunk: SOAR chunking - extract reusable pattern from success
- consolidate: Merge similar memories
- decay_edges: Decay edge weights for unused relationships
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
    # Code-assisted (surfaces facts)
    similar_recent,
    suggest_edges,
    # Utility
    recall_by_file_patterns,
    chunk,
    consolidate,
    decay_edges,
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
    "chunk",
    "consolidate",
    "decay_edges",
]
