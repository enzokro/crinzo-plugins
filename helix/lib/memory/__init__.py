"""Memory layer for Helix.

8 Primitives:
- store: Store new insight with semantic deduplication
- recall: Semantic search ranked by relevance x effectiveness
- get: Retrieve specific insight by name
- feedback: Update effectiveness based on outcome
- decay: Decay dormant insights toward neutral
- prune: Remove ineffective insights
- count: Lightweight total insight count
- health: System status check
"""

from .core import (
    store,
    recall,
    get,
    feedback,
    decay,
    prune,
    count,
    health,
)

__all__ = [
    "store",
    "recall",
    "get",
    "feedback",
    "decay",
    "prune",
    "count",
    "health",
]
