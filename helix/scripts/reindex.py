#!/usr/bin/env python3
"""Re-embed all insights with the current embedding model.

Usage:
    python scripts/reindex.py          # Re-embed insights with NULL embeddings only
    python scripts/reindex.py --force  # Re-embed ALL insights (for model swaps)

Idempotent: without --force, skips insights that already have non-NULL embeddings.
"""

import argparse
import sys
from pathlib import Path

# Add project root for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.memory.embeddings import embed, to_blob, EMBED_DIM
from lib.db.connection import get_db, write_lock


def reindex(force: bool = False) -> dict:
    """Re-embed insights in the database.

    Args:
        force: If True, re-embed all insights regardless of current embedding state.
               If False, only re-embed insights with NULL embeddings.

    Returns: {"reindexed": int, "skipped": int, "failed": int, "total": int}
    """
    db = get_db()

    if force:
        rows = db.execute("SELECT id, name, content FROM insight").fetchall()
    else:
        rows = db.execute("SELECT id, name, content FROM insight WHERE embedding IS NULL").fetchall()

    total = len(rows)
    reindexed = 0
    skipped = 0
    failed = 0

    for row in rows:
        content = row["content"]
        emb = embed(content, is_query=False)

        if emb is None:
            failed += 1
            print(f"  FAILED: {row['name']} (embedding model unavailable)")
            continue

        if len(emb) != EMBED_DIM:
            failed += 1
            print(f"  FAILED: {row['name']} (unexpected dim {len(emb)}, expected {EMBED_DIM})")
            continue

        blob = to_blob(emb)
        with write_lock():
            db.execute("UPDATE insight SET embedding = ? WHERE id = ?", (blob, row["id"]))
            db.commit()

        reindexed += 1
        print(f"  Re-embedded {reindexed}/{total}: {row['name']}")

    return {"reindexed": reindexed, "skipped": skipped, "failed": failed, "total": total}


def main():
    parser = argparse.ArgumentParser(description="Re-embed insights with current model")
    parser.add_argument("--force", action="store_true",
                        help="Re-embed ALL insights, not just those with NULL embeddings")
    args = parser.parse_args()

    mode = "all insights (--force)" if args.force else "NULL embeddings only"
    print(f"Reindexing: {mode}")
    print(f"Model dimension: {EMBED_DIM}")
    print()

    result = reindex(force=args.force)

    print()
    print(f"Done. Re-embedded {result['reindexed']}/{result['total']} insights.")
    if result["failed"]:
        print(f"  Failed: {result['failed']}")


if __name__ == "__main__":
    main()
