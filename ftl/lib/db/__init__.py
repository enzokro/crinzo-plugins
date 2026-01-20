"""FTL Database Package - fastsql backend for all storage operations."""

from .schema import (
    Memory, MemoryEdge, Campaign, Workspace,
    Archive, Exploration, PhaseState, Event,
    ExplorerResult, Plan, Benchmark,
    embed_to_blob, blob_to_embed
)
from .connection import get_db, init_db, reset_db, DB_PATH
from .embeddings import embed, similarity, is_available, cosine_similarity_blob
from .locks import db_write_lock

__all__ = [
    # Schema
    'Memory', 'MemoryEdge', 'Campaign', 'Workspace',
    'Archive', 'Exploration', 'PhaseState', 'Event',
    'ExplorerResult', 'Plan', 'Benchmark',
    'embed_to_blob', 'blob_to_embed',
    # Connection
    'get_db', 'init_db', 'reset_db', 'DB_PATH',
    # Embeddings
    'embed', 'similarity', 'is_available', 'cosine_similarity_blob',
    # Concurrency
    'db_write_lock',
]
