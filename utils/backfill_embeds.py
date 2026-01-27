#!/usr/bin/env python3
"""Backfill embeddings for helix memories.

Finds memories with NULL embeddings and computes them using sentence-transformers.
Safe to run multiple times - only processes memories that need it.

Usage:
    python backfill_embeds.py                    # Backfill current project's .helix/helix.db
    python backfill_embeds.py --db /path/to.db   # Backfill specific database
    python backfill_embeds.py --dry-run          # Show what would be done
    python backfill_embeds.py --verbose          # Show detailed progress
"""

import argparse
import sqlite3
import struct
import sys
from pathlib import Path
from typing import Optional, Tuple, List

# ---------------------------------------------------------------------------
# Embedding functions (self-contained, no external helix dependency)
# ---------------------------------------------------------------------------

_model = None
_loaded = False


def load_model():
    """Lazy load the sentence-transformers model."""
    global _model, _loaded
    if _loaded:
        return _model
    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        print("Model loaded: all-MiniLM-L6-v2 (384 dimensions)")
    except ImportError:
        print("ERROR: sentence-transformers not installed")
        print("  pip install sentence-transformers")
        sys.exit(1)
    _loaded = True
    return _model


def embed(text: str) -> Optional[Tuple[float, ...]]:
    """Generate 384-dim embedding for text."""
    model = load_model()
    if model is None:
        return None
    if len(text) > 8000:
        text = text[:8000]
    vec = model.encode(text, convert_to_numpy=True)
    return tuple(float(x) for x in vec)


def to_blob(emb: Tuple[float, ...]) -> bytes:
    """Pack embedding tuple into SQLite BLOB format."""
    return struct.pack(f"{len(emb)}f", *emb)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------

def find_db(specified: Optional[str] = None) -> Path:
    """Find the helix database to use."""
    if specified:
        p = Path(specified)
        if not p.exists():
            print(f"ERROR: Database not found: {p}")
            sys.exit(1)
        return p

    # Look in current directory
    local = Path(".helix/helix.db")
    if local.exists():
        return local

    print("ERROR: No .helix/helix.db found in current directory")
    print("  Use --db to specify path, or run from project root")
    sys.exit(1)


def get_memories_needing_embeddings(db: sqlite3.Connection) -> List[dict]:
    """Get all memories with NULL embeddings."""
    db.row_factory = sqlite3.Row
    rows = db.execute(
        "SELECT name, type, trigger, resolution FROM memory WHERE embedding IS NULL"
    ).fetchall()
    return [dict(r) for r in rows]


def update_embedding(db: sqlite3.Connection, name: str, blob: bytes) -> None:
    """Update a memory's embedding."""
    db.execute("UPDATE memory SET embedding = ? WHERE name = ?", (blob, name))


# ---------------------------------------------------------------------------
# Main backfill logic
# ---------------------------------------------------------------------------

def backfill(db_path: Path, dry_run: bool = False, verbose: bool = False) -> dict:
    """
    Backfill embeddings for all memories that need them.

    Returns dict with counts: {total, processed, failed, skipped}
    """
    db = sqlite3.connect(db_path)
    memories = get_memories_needing_embeddings(db)

    stats = {"total": len(memories), "processed": 0, "failed": 0, "skipped": 0}

    if not memories:
        return stats

    # Load model once (lazy, so first embed() call loads it)
    if not dry_run:
        load_model()

    for i, mem in enumerate(memories, 1):
        name = mem["name"]
        text = f"{mem['trigger']} {mem['resolution']}"

        if verbose:
            print(f"[{i}/{len(memories)}] {mem['type']}: {name[:50]}...")

        if dry_run:
            stats["skipped"] += 1
            continue

        try:
            emb = embed(text)
            if emb is None:
                print(f"  WARNING: Failed to embed {name}")
                stats["failed"] += 1
                continue

            blob = to_blob(emb)
            update_embedding(db, name, blob)
            stats["processed"] += 1

            if verbose:
                print(f"  OK ({len(emb)} dims)")

        except Exception as e:
            print(f"  ERROR: {name}: {e}")
            stats["failed"] += 1

    if not dry_run:
        db.commit()

    db.close()
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Backfill embeddings for helix memories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backfill_embeds.py                  # Current project
  python backfill_embeds.py --dry-run        # Preview only
  python backfill_embeds.py --db ~/.helix/helix.db --verbose
        """
    )
    parser.add_argument(
        "--db",
        help="Path to helix.db (default: .helix/helix.db)"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed progress"
    )
    args = parser.parse_args()

    db_path = find_db(args.db)
    print(f"Database: {db_path}")

    if args.dry_run:
        print("DRY RUN - no changes will be made\n")

    stats = backfill(db_path, dry_run=args.dry_run, verbose=args.verbose)

    # Summary
    print()
    print(f"Total memories needing embeddings: {stats['total']}")
    if args.dry_run:
        print(f"Would process: {stats['total']}")
    else:
        print(f"Successfully processed: {stats['processed']}")
        if stats["failed"]:
            print(f"Failed: {stats['failed']}")

    if stats["total"] == 0:
        print("All memories already have embeddings!")
    elif not args.dry_run and stats["failed"] == 0:
        print("Done!")

    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
