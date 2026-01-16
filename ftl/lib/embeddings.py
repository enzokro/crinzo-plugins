#!/usr/bin/env python3
"""Semantic embeddings with graceful fallback to string matching."""

from functools import lru_cache
from difflib import SequenceMatcher

_model = None
_available = None


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


@lru_cache(maxsize=1000)
def embed(text: str) -> tuple | None:
    """Get embedding for text. Returns tuple for LRU cache hashability."""
    model = _load_model()
    if model is None:
        return None
    return tuple(model.encode(text, convert_to_numpy=True).tolist())


def similarity(text1: str, text2: str) -> float:
    """Compute similarity between texts (0.0 to 1.0).

    Uses cosine similarity on embeddings if available,
    otherwise falls back to SequenceMatcher ratio.
    """
    vec1, vec2 = embed(text1), embed(text2)
    if vec1 is not None and vec2 is not None:
        import numpy as np
        v1, v2 = np.array(vec1), np.array(vec2)
        return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
