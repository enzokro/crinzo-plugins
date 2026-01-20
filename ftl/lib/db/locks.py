"""Shared concurrency primitives for FTL database operations.

Provides cross-module synchronization for database writes to prevent
race conditions when multiple modules access the database concurrently.
"""

import threading

# Global write lock for coordinating database writes across all modules.
# This lock should be acquired by any module performing write operations
# that must be atomic or could conflict with concurrent operations.
#
# Usage:
#     from lib.db.locks import db_write_lock
#     with db_write_lock:
#         # perform database writes
#
# Note: Using RLock (reentrant lock) to allow nested acquisition within
# the same thread. This prevents deadlocks when functions that hold the lock
# call other functions that also require the lock (e.g., observer -> memory).
# For true multi-process safety, rely on SQLite's WAL mode and transaction isolation.
db_write_lock = threading.RLock()
