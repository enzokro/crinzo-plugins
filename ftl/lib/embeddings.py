#!/usr/bin/env python3
"""Semantic embeddings with graceful fallback to string matching."""

from functools import lru_cache
from difflib import SequenceMatcher
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
def embed(text: str) -> tuple | None:
    """Get embedding for text. Returns tuple for LRU cache hashability.

    Args:
        text: Text to embed. Empty strings return None.

    Returns:
        Tuple of floats (embedding) or None if unavailable/invalid input.
    """
    # Input validation
    if text is None or not text.strip():
        return None

    model = _load_model()
    if model is None:
        return None

    # encode() returns numpy array directly, tolist() converts to Python list
    return tuple(model.encode(text).tolist())


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
    # Handle None/empty inputs
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
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
