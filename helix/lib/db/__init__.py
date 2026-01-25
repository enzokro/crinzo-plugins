"""Database layer for Helix - semantic memory with relationships.

Note: Plan, Task, Workspace have been removed. Task management is now
handled by Claude Code's native Task system.

Embeddings are in lib/memory/embeddings.py - import directly from there.
"""

from .connection import get_db, write_lock, init_db
from .schema import Memory, MemoryEdge

__all__ = [
    "get_db", "write_lock", "init_db",
    "Memory", "MemoryEdge",
]
