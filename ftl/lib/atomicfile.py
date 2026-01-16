#!/usr/bin/env python3
"""Simple file locking for atomic JSON operations."""

import fcntl
import json
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
    """Atomically read, modify, and write JSON file.

    Args:
        path: JSON file path
        update_fn: Function that receives data dict, modifies in place, returns result

    Returns:
        Whatever update_fn returns
    """
    with locked_file(path) as f:
        data = json.load(f)
        result = update_fn(data)
        f.seek(0)
        f.truncate()
        json.dump(data, f, indent=2)
    return result
