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
    """Lazy load embedding model.

    Tries local cache first (no network) to avoid httpx timeouts when
    HuggingFace Hub is slow/unreachable. Falls back to full download
    only when model isn't cached yet.
    """
    global _model, _loaded
    if _loaded:
        return _model
    try:
        with _suppress_output():
            from sentence_transformers import SentenceTransformer
            try:
                # Local cache only — no network requests
                _model = SentenceTransformer(
                    "Snowflake/snowflake-arctic-embed-m-v1.5",
                    truncate_dim=EMBED_DIM,
                    local_files_only=True,
                )
            except Exception:
                # Model not cached yet — download it
                _model = SentenceTransformer(
                    "Snowflake/snowflake-arctic-embed-m-v1.5",
                    truncate_dim=EMBED_DIM,
                )
    except Exception:
        _model = None
    _loaded = True
    return _model


def warmup():
    """Pre-load embedding model into OS page cache.

    Called during session init (background) so subsequent in-process
    loads skip disk I/O.
    """
    return _load() is not None


def embed(text: str, is_query: bool = False) -> Optional[Tuple[float, ...]]:
    """Generate 256-dim embedding for text.

    Args:
        text: Input text to embed.
        is_query: True for search queries (adds retrieval instruction prefix).
                  False for documents/insights (plain encoding).

    Returns None if embeddings unavailable.
    Cached by (text, is_query) for performance. Truncation applied before
    cache lookup so strings >MAX_TEXT_CHARS that truncate identically share a slot.
    """
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS]
    return _embed_cached(text, is_query)


@lru_cache(maxsize=2000)
def _embed_cached(text: str, is_query: bool) -> Optional[Tuple[float, ...]]:
    """Cached embedding computation. Called after truncation."""
    model = _load()
    if model is None:
        return None

    if is_query:
        vec = model.encode([text], prompt_name="query", normalize_embeddings=True)[0]
    else:
        vec = model.encode([text], normalize_embeddings=True)[0]

    return tuple(float(x) for x in vec)


def to_blob(emb: Tuple[float, ...]) -> bytes:
    """Convert embedding tuple to SQLite BLOB."""
    return struct.pack(f"{len(emb)}f", *emb)


def build_embedding_matrix(blobs):
    """Build numpy matrix from embedding BLOBs for vectorized similarity."""
    import numpy as np
    joined = b''.join(blobs)
    count = len(joined) // (EMBED_DIM * 4)
    return np.frombuffer(joined, dtype=np.float32).reshape(count, -1)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "warmup":
        print("ok" if warmup() else "unavailable")
    else:
        print("Usage: embeddings.py warmup")
