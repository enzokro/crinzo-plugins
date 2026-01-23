"""Memory layer for Helix.

Exports the core API:
- store: Store new memory with semantic deduplication
- recall: Semantic search ranked by relevance x effectiveness x recency
- feedback: Close the learning loop (THE critical mechanism)
- chunk: SOAR chunking - extract reusable pattern from success
- relate: Create relationships between memories
- connected: Graph traversal for related knowledge
- health: System status check
- prune: Remove ineffective memories
- consolidate: Merge similar memories
- decay: Find dormant memories
- get: Retrieve specific memory by name
"""

from .core import (
    store,
    recall,
    feedback,
    chunk,
    relate,
    connected,
    health,
    prune,
    consolidate,
    decay,
    get,
)
from .embeddings import is_available as embeddings_available
from .meta import assess_approach

__all__ = [
    "store",
    "recall",
    "feedback",
    "chunk",
    "relate",
    "connected",
    "health",
    "prune",
    "consolidate",
    "decay",
    "get",
    "embeddings_available",
    "assess_approach",
]
