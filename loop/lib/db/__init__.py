"""Database layer for loop memory system."""

from .connection import get_db, init_db, reset_db
from .schema import Memory
from .embeddings import embed, similarity, is_available

__all__ = [
    "get_db",
    "init_db",
    "reset_db",
    "Memory",
    "embed",
    "similarity",
    "is_available",
]
