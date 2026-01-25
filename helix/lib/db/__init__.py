"""Database layer for Helix - semantic memory with relationships.

Note: Plan, Task, Workspace have been removed. Task management is now
handled by Claude Code's native Task system.
"""

from .connection import get_db, write_lock, init_db
from .schema import Memory, MemoryEdge, Exploration
from .embeddings import embed, similarity, cosine_similarity, is_available

__all__ = [
    "get_db", "write_lock", "init_db",
    "Memory", "MemoryEdge", "Exploration",
    "embed", "similarity", "cosine_similarity", "is_available",
]
