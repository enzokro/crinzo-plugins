"""Semantic embeddings for meaning-based retrieval.

Uses sentence-transformers with all-MiniLM-L6-v2 (384 dimensions).
Falls back to simple text matching if model unavailable.
"""

import struct
from functools import lru_cache
from typing import Optional, Tuple
import os

# Lazy loading
_model = None
_model_loaded = False

# Constants
EMBEDDING_DIM = 384
EMBEDDING_BYTES = EMBEDDING_DIM * 4
CACHE_SIZE = int(os.environ.get("HELIX_EMBEDDING_CACHE", "2000"))


def _load_model():
    """Lazy load the embedding model."""
    global _model, _model_loaded

    if _model_loaded:
        return _model

    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        _model_loaded = True
    except ImportError:
        _model = None
        _model_loaded = True

    return _model


def is_available() -> bool:
    """Check if embedding model is available."""
    return _load_model() is not None


@lru_cache(maxsize=CACHE_SIZE)
def embed(text: str) -> Optional[Tuple[float, ...]]:
    """Generate embedding for text.

    Returns tuple of 384 floats, or None if model unavailable.
    """
    model = _load_model()
    if model is None:
        return None

    # Truncate very long texts
    if len(text) > 8000:
        text = text[:8000]

    embedding = model.encode(text, convert_to_numpy=True)
    return tuple(float(x) for x in embedding)


def embed_to_blob(embedding: Tuple[float, ...]) -> bytes:
    """Convert embedding tuple to SQLite BLOB."""
    return struct.pack(f"{len(embedding)}f", *embedding)


def blob_to_embed(blob: bytes) -> Tuple[float, ...]:
    """Convert SQLite BLOB to embedding tuple."""
    count = len(blob) // 4
    return struct.unpack(f"{count}f", blob)


def cosine_similarity(emb1: Tuple[float, ...], emb2: Tuple[float, ...]) -> float:
    """Compute cosine similarity between two embeddings."""
    dot = sum(a * b for a, b in zip(emb1, emb2))
    norm1 = sum(a * a for a in emb1) ** 0.5
    norm2 = sum(b * b for b in emb2) ** 0.5

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def cosine_similarity_blob(blob1: bytes, blob2: bytes) -> float:
    """Compute cosine similarity between two embedding BLOBs."""
    return cosine_similarity(blob_to_embed(blob1), blob_to_embed(blob2))


def similarity(text1: str, text2: str) -> float:
    """Compute semantic similarity between two texts.

    Returns 0.0-1.0 where 1.0 is identical meaning.
    Falls back to sequence matching if model unavailable.
    """
    emb1 = embed(text1)
    emb2 = embed(text2)

    if emb1 is None or emb2 is None:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

    return cosine_similarity(emb1, emb2)
