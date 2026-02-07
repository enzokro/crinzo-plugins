"""Semantic embeddings for meaning-based retrieval.

Uses Snowflake arctic-embed-m-v1.5 for 256-dim embeddings (Matryoshka truncation).
Asymmetric encoding: query prompt for searches, plain encode for documents.
Falls back gracefully when unavailable.
"""

import os
import struct
import sys
from contextlib import contextmanager
from functools import lru_cache
from typing import Optional, Tuple

_model = None
_loaded = False

# Matryoshka truncation dimension (768 -> 256, 98.4% quality retention)
EMBED_DIM = 256

# Max text length (~500 tokens)
MAX_TEXT_CHARS = 2000


@contextmanager
def _suppress_output():
    """Suppress stdout/stderr during model loading."""
    stdout_fd = sys.stdout.fileno()
    stderr_fd = sys.stderr.fileno()
    saved_stdout = os.dup(stdout_fd)
    saved_stderr = os.dup(stderr_fd)
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, stdout_fd)
        os.dup2(devnull, stderr_fd)
        os.close(devnull)
        yield
    finally:
        os.dup2(saved_stdout, stdout_fd)
        os.dup2(saved_stderr, stderr_fd)
        os.close(saved_stdout)
        os.close(saved_stderr)


def _load():
    """Lazy load embedding model."""
    global _model, _loaded
    if _loaded:
        return _model
    try:
        with _suppress_output():
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(
                "Snowflake/snowflake-arctic-embed-m-v1.5",
                truncate_dim=EMBED_DIM,
            )
    except ImportError:
        _model = None
    _loaded = True
    return _model


@lru_cache(maxsize=2000)
def embed(text: str, is_query: bool = False) -> Optional[Tuple[float, ...]]:
    """Generate 256-dim embedding for text.

    Args:
        text: Input text to embed.
        is_query: True for search queries (adds retrieval instruction prefix).
                  False for documents/insights (plain encoding).

    Returns None if embeddings unavailable.
    Cached by (text, is_query) for performance.
    """
    model = _load()
    if model is None:
        return None
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]

    if is_query:
        vec = model.encode([text], prompt_name="query", normalize_embeddings=True)[0]
    else:
        vec = model.encode([text], normalize_embeddings=True)[0]

    return tuple(float(x) for x in vec)


def to_blob(emb: Tuple[float, ...]) -> bytes:
    """Convert embedding tuple to SQLite BLOB."""
    return struct.pack(f"{len(emb)}f", *emb)


def from_blob(blob: bytes) -> Tuple[float, ...]:
    """Convert SQLite BLOB to embedding tuple."""
    return struct.unpack(f"{len(blob)//4}f", blob)


def cosine(a: Tuple[float, ...], b: Tuple[float, ...]) -> float:
    """Cosine similarity between embeddings (0-1)."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0
