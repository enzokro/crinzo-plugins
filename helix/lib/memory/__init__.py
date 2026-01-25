"""Memory layer for Helix.

Exports the core API:
- store: Store new memory with semantic deduplication
- recall: Semantic search ranked by relevance x effectiveness x recency
- recall_by_file_patterns: Search by file patterns
- feedback_from_verification: Verification-based feedback (THE critical mechanism)
- chunk: SOAR chunking - extract reusable pattern from success
- health: System status check
- prune: Remove ineffective memories
- consolidate: Merge similar memories
- decay: Find dormant memories
- get: Retrieve specific memory by name
"""

from .core import (
    store,
    recall,
    recall_by_file_patterns,
    feedback_from_verification,
    chunk,
    health,
    prune,
    consolidate,
    decay,
    get,
)
from .embeddings import is_available as embeddings_available

__all__ = [
    "store",
    "recall",
    "recall_by_file_patterns",
    "feedback_from_verification",
    "chunk",
    "health",
    "prune",
    "consolidate",
    "decay",
    "get",
    "embeddings_available",
]
