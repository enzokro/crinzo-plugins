"""Shared logging for helix hooks."""

from datetime import datetime, timezone

from paths import get_helix_dir


def log_error(context: str, error: Exception):
    """Log error to extraction.log for diagnostics."""
    try:
        log_file = get_helix_dir() / "extraction.log"
        ts = datetime.now(timezone.utc).isoformat()
        with open(log_file, 'a') as f:
            f.write(f"{ts} | ERROR | {context} | {type(error).__name__}: {error}\n")
    except Exception:
        pass  # logging must never crash the hook
