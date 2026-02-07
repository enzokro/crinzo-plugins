"""Database layer for Helix - semantic memory with relationships.

Note: Plan, Task, and Workspace are handled by Claude Code's native
Task system with metadata.

Embeddings are in lib/memory/embeddings.py - import directly from there.
"""

from .connection import get_db, write_lock, init_db

__all__ = [
    "get_db", "write_lock", "init_db",
]
