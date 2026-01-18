"""Embedding storage and retrieval with database backend.

Provides semantic similarity using sentence-transformers with LRU caching.
Falls back to string matching when sentence-transformers is unavailable.
"""

from functools import lru_cache
from difflib import SequenceMatcher
from typing import Optional
import struct
import os

_model = None
_available = None

# Configurable cache size via environment variable
_CACHE_SIZE = int(os.environ.get('FTL_EMBEDDING_CACHE_SIZE', '5000'))


def _load_model():
    """Lazy load sentence-transformers. Only runs once."""
    global _model, _available
    if _available is None:
        try:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer('all-MiniLM-L6-v2')
            _available = True
        except ImportError:
            _available = False
    return _model


def is_available() -> bool:
    """Check if semantic embeddings are available."""
    _load_model()
    return _available


@lru_cache(maxsize=_CACHE_SIZE)
def embed(text: str) -> Optional[tuple]:
    """Generate 384-dim embedding, cached in memory.

    Args:
        text: Text to embed. Empty strings return None.

    Returns:
        Tuple of 384 floats or None if unavailable/invalid input.
    """
    if text is None or not text.strip():
        return None

    model = _load_model()
    if model is None:
        return None

    return tuple(model.encode(text).tolist())


def embed_to_blob(embedding: tuple) -> Optional[bytes]:
    """Serialize embedding to SQLite BLOB (1536 bytes for 384 floats).

    Args:
        embedding: Tuple of floats from embed()

    Returns:
        Bytes object suitable for BLOB storage, or None.
    """
    if embedding is None:
        return None
    return struct.pack(f'{len(embedding)}f', *embedding)


def blob_to_embed(blob: bytes) -> Optional[tuple]:
    """Deserialize BLOB to embedding tuple.

    Args:
        blob: Bytes from database BLOB column

    Returns:
        Tuple of floats, or None if blob is None.
    """
    if blob is None:
        return None
    count = len(blob) // 4
    return struct.unpack(f'{count}f', blob)


def similarity(text1: str, text2: str) -> float:
    """Compute similarity between texts (0.0 to 1.0).

    Uses cosine similarity on embeddings if available,
    otherwise falls back to SequenceMatcher ratio.

    Args:
        text1: First text to compare
        text2: Second text to compare

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0

    vec1, vec2 = embed(text1), embed(text2)

    if vec1 is not None and vec2 is not None:
        import numpy as np
        v1, v2 = np.array(vec1), np.array(vec2)
        norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
        if norm_product == 0:
            return 0.0
        return float(np.dot(v1, v2) / norm_product)

    # Fallback: string similarity
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()


def cosine_similarity_blob(blob1: bytes, blob2: bytes) -> float:
    """Compute cosine similarity from stored BLOBs.

    Args:
        blob1: First embedding as BLOB
        blob2: Second embedding as BLOB

    Returns:
        Cosine similarity between 0.0 and 1.0
    """
    if not blob1 or not blob2:
        return 0.0

    import numpy as np
    v1 = np.array(blob_to_embed(blob1))
    v2 = np.array(blob_to_embed(blob2))

    norm_product = np.linalg.norm(v1) * np.linalg.norm(v2)
    if norm_product == 0:
        return 0.0

    return float(np.dot(v1, v2) / norm_product)
