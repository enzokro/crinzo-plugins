"""Embedding layer for lattice semantic memory.

Provides semantic search capabilities while preserving lattice's core soul:
- Decisions accumulate and become queryable
- Patterns emerge and get tracked with signals
- Signal history learns what works

Embeddings augment, they don't replace. Graceful degradation when unavailable.
"""

from pathlib import Path
import json
import hashlib

try:
    from sentence_transformers import SentenceTransformer
    import numpy as np
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False

MODEL_NAME = "all-MiniLM-L6-v2"
DIMS = 384


class EmbeddingStore:
    """Manages vector embeddings for lattice decisions.

    Supports incremental embedding (only re-embeds changed decisions)
    and hybrid retrieval (exact + semantic matches).
    """

    def __init__(self, lattice_dir=".lattice"):
        self.lattice_dir = Path(lattice_dir)
        self.vectors_dir = self.lattice_dir / "vectors"
        self._model = None  # Lazy load

    @property
    def available(self) -> bool:
        """Check if embedding dependencies are available."""
        return EMBEDDINGS_AVAILABLE

    def _load_model(self):
        """Lazy load the sentence transformer model."""
        if self._model is None:
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    def _content_hash(self, text: str) -> str:
        """Generate short hash for change detection."""
        return hashlib.md5(text.encode()).hexdigest()[:12]

    def _decision_content(self, decision: dict) -> str:
        """Build embeddable content from decision fields.

        Includes full content (not truncated) for better semantic matching.
        """
        parts = [
            decision.get("slug", ""),
            decision.get("path", ""),
            decision.get("delta", ""),
            decision.get("traces", ""),
            decision.get("rationale", ""),
            " ".join(decision.get("concepts", [])),
            " ".join(decision.get("tags", [])),
        ]
        return " ".join(p for p in parts if p)

    def embed_decisions(self, decisions: dict) -> int:
        """Incrementally embed decisions.

        Only embeds new or modified decisions based on content hash.
        Returns count of decisions embedded.
        """
        if not self.available:
            return 0

        self.vectors_dir.mkdir(parents=True, exist_ok=True)
        meta_path = self.vectors_dir / "meta.json"
        vectors_path = self.vectors_dir / "decisions.npz"

        # Load existing metadata
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            meta = {"model": MODEL_NAME, "dims": DIMS, "embedded": {}, "seqs": []}

        # Find decisions needing embedding
        to_embed = []
        for seq, decision in decisions.items():
            content = self._decision_content(decision)
            content_hash = self._content_hash(content)

            existing = meta["embedded"].get(seq)
            if not existing or existing.get("hash") != content_hash:
                to_embed.append((seq, content, content_hash))

        if not to_embed:
            return 0

        # Embed new content
        model = self._load_model()
        texts = [t[1] for t in to_embed]
        new_vectors = model.encode(texts, normalize_embeddings=True)

        # Load existing vectors or create empty array
        if vectors_path.exists() and meta["seqs"]:
            data = np.load(vectors_path)
            existing_vectors = data["vectors"]
            existing_seqs = list(meta["seqs"])
        else:
            existing_vectors = np.zeros((0, DIMS))
            existing_seqs = []

        # Handle updates vs new additions
        updated_indices = []
        new_entries = []

        for i, (seq, content, content_hash) in enumerate(to_embed):
            if seq in existing_seqs:
                # Update existing embedding
                idx = existing_seqs.index(seq)
                updated_indices.append((idx, i))
            else:
                # New embedding
                new_entries.append((seq, i, content_hash))

        # Apply updates to existing vectors
        for old_idx, new_idx in updated_indices:
            existing_vectors[old_idx] = new_vectors[new_idx]
            seq = to_embed[new_idx][0]
            meta["embedded"][seq] = {"hash": to_embed[new_idx][2]}

        # Append new vectors
        if new_entries:
            new_vecs = np.array([new_vectors[i] for _, i, _ in new_entries])
            existing_vectors = np.vstack([existing_vectors, new_vecs])
            for seq, i, content_hash in new_entries:
                existing_seqs.append(seq)
                meta["embedded"][seq] = {"hash": content_hash}

        # Save
        np.savez(vectors_path, vectors=existing_vectors)
        meta["seqs"] = existing_seqs
        meta_path.write_text(json.dumps(meta, indent=2))

        return len(to_embed)

    def query(self, text: str, top_k: int = 10) -> list[tuple[str, float]]:
        """Query for semantically similar decisions.

        Returns list of (seq, similarity) pairs, sorted by similarity descending.
        """
        if not self.available:
            return []

        vectors_path = self.vectors_dir / "decisions.npz"
        meta_path = self.vectors_dir / "meta.json"

        if not vectors_path.exists() or not meta_path.exists():
            return []

        model = self._load_model()
        query_vec = model.encode(text, normalize_embeddings=True)

        data = np.load(vectors_path)
        vectors = data["vectors"]

        if len(vectors) == 0:
            return []

        meta = json.loads(meta_path.read_text())
        seqs = meta.get("seqs", [])

        if len(seqs) != len(vectors):
            # Metadata mismatch - return empty rather than crash
            return []

        # Cosine similarity (vectors already normalized)
        similarities = vectors @ query_vec

        # Top-k results
        k = min(top_k, len(similarities))
        top_indices = np.argsort(similarities)[-k:][::-1]

        return [(seqs[i], float(similarities[i])) for i in top_indices]

    def find_similar(self, seq: str, top_k: int = 5, threshold: float = 0.7) -> list[tuple[str, float]]:
        """Find decisions similar to a given decision.

        Useful for building semantic edges between related decisions.
        """
        if not self.available:
            return []

        vectors_path = self.vectors_dir / "decisions.npz"
        meta_path = self.vectors_dir / "meta.json"

        if not vectors_path.exists() or not meta_path.exists():
            return []

        meta = json.loads(meta_path.read_text())
        seqs = meta.get("seqs", [])

        if seq not in seqs:
            return []

        data = np.load(vectors_path)
        vectors = data["vectors"]

        idx = seqs.index(seq)
        target_vec = vectors[idx]

        # Cosine similarity with all vectors
        similarities = vectors @ target_vec

        # Get top-k (excluding self)
        results = []
        sorted_indices = np.argsort(similarities)[::-1]

        for i in sorted_indices:
            if seqs[i] != seq and similarities[i] >= threshold:
                results.append((seqs[i], float(similarities[i])))
                if len(results) >= top_k:
                    break

        return results

    def clear(self):
        """Clear all embeddings. Useful for full rebuild."""
        if self.vectors_dir.exists():
            for f in self.vectors_dir.iterdir():
                f.unlink()
