"""Database layer for Helix - semantic memory with relationships."""

from .connection import get_db, write_lock, init_db
from .schema import Memory, MemoryEdge, Exploration, Plan, Task, Workspace
from .embeddings import embed, similarity, cosine_similarity, is_available

__all__ = [
    "get_db", "write_lock", "init_db",
    "Memory", "MemoryEdge", "Exploration", "Plan", "Task", "Workspace",
    "embed", "similarity", "cosine_similarity", "is_available",
]
