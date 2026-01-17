#!/usr/bin/env python3
"""Crash-safe atomic JSON operations with temp-file + rename pattern."""

import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def locked_file(path: Path):
    """Acquire exclusive lock on file for read-modify-write."""
    with open(path, 'r+') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield f
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def atomic_json_update(path: Path, update_fn) -> any:
    """Atomically read, modify, and write JSON file with crash safety.

    Uses temp-file + rename pattern for crash safety:
    1. Read data under lock
    2. Apply update function
    3. Write to temp file in same directory
    4. fsync to ensure data is on disk
    5. Atomic rename (POSIX guarantees this is atomic on same filesystem)

    This ensures that a crash at any point leaves either the old or new
    file intact, never a partial write.

    Args:
        path: JSON file path
        update_fn: Function that receives data dict, modifies in place, returns result

    Returns:
        Whatever update_fn returns
    """
    path = Path(path)
    temp_path = None

    with locked_file(path) as f:
        data = json.load(f)
        result = update_fn(data)

        # Write to temp file in same directory (required for atomic rename)
        fd, temp_path = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.stem}.",
            suffix=".tmp"
        )
        try:
            with os.fdopen(fd, 'w') as tf:
                json.dump(data, tf, indent=2)
                tf.flush()
                os.fsync(tf.fileno())  # Ensure data is on disk before rename

            # Atomic rename (POSIX guarantees atomicity on same filesystem)
            os.rename(temp_path, path)
            temp_path = None  # Successfully renamed, don't cleanup
        finally:
            # Cleanup temp file if rename failed
            if temp_path and os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

    return result


def atomic_write(path: Path, data: dict) -> None:
    """Write JSON file atomically (for new files or complete overwrites).

    Unlike atomic_json_update, this doesn't require the file to exist.

    Args:
        path: JSON file path
        data: Data dict to write
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".tmp"
    )
    try:
        with os.fdopen(fd, 'w') as tf:
            json.dump(data, tf, indent=2)
            tf.flush()
            os.fsync(tf.fileno())

        os.rename(temp_path, path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
            except OSError:
                pass
