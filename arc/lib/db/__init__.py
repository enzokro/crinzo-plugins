"""Database layer for arc."""
from .connection import get_db, write_lock
from .embeddings import embed, similarity, is_available

__all__ = ["get_db", "write_lock", "embed", "similarity", "is_available"]
