"""Semantic embeddings for meaning-based retrieval."""

import struct
from functools import lru_cache
from typing import Optional, Tuple

_model = None
_loaded = False


def _load():
    """Lazy load embedding model."""
    global _model, _loaded
    if _loaded:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    except ImportError:
        _model = None
    _loaded = True
    return _model


def is_available() -> bool:
    """Check if embeddings are available."""
    return _load() is not None


@lru_cache(maxsize=2000)
def embed(text: str) -> Optional[Tuple[float, ...]]:
    """Generate 384-dim embedding for text."""
    model = _load()
    if model is None:
        return None
    if len(text) > 8000:
        text = text[:8000]
    vec = model.encode(text, convert_to_numpy=True)
    return tuple(float(x) for x in vec)


def to_blob(emb: Tuple[float, ...]) -> bytes:
    """Convert embedding to SQLite BLOB."""
    return struct.pack(f"{len(emb)}f", *emb)


def from_blob(blob: bytes) -> Tuple[float, ...]:
    """Convert BLOB to embedding."""
    return struct.unpack(f"{len(blob)//4}f", blob)


def cosine(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    """Cosine similarity between embeddings."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def similarity(text1: str, text2: str) -> float:
    """Semantic similarity between texts (0-1)."""
    e1, e2 = embed(text1), embed(text2)
    if e1 is None or e2 is None:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    return cosine(e1, e2)
