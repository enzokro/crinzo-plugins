#!/usr/bin/env python3
"""SessionEnd hook - process learning queue and log session summary.

Triggered by: SessionEnd lifecycle event
Replaces: scripts/hooks/session-end.sh

Does:
1. Count pending learning queue items
2. Log session end to .helix/session.log
3. Cleanup old queue files (>7 days)

Note: The bash script had auto-store logic calling a non-existent
`similar-recent` CLI command. That dead code is not ported.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def get_helix_dir() -> Path:
    """Find .helix directory via ancestor search."""
    project_dir = os.environ.get("HELIX_PROJECT_DIR")
    if project_dir:
        helix_dir = Path(project_dir) / ".helix"
        helix_dir.mkdir(exist_ok=True)
        return helix_dir

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        helix_dir = parent / ".helix"
        if helix_dir.exists():
            return helix_dir

    helix_dir = cwd / ".helix"
    helix_dir.mkdir(exist_ok=True)
    return helix_dir


def log_event(log_file: Path, *parts):
    """Append log entry."""
    ts = datetime.now(timezone.utc).isoformat()
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(f"{ts} | " + " | ".join(str(p) for p in parts) + "\n")


def count_pending_items(queue_dir: Path) -> int:
    """Count pending queue items."""
    if not queue_dir.exists():
        return 0
    return len(list(queue_dir.glob("*.json")))


def log_pending_details(queue_dir: Path, log_file: Path):
    """Log details of pending queue items."""
    if not queue_dir.exists():
        return

    for f in queue_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            agent_id = f.stem
            candidate_count = len(data.get("candidates", []))
            log_event(log_file, "PENDING", f"agent={agent_id}", f"candidates={candidate_count}")
        except Exception:
            pass


def cleanup_old_files(queue_dir: Path, max_age_days: int = 7):
    """Remove queue files older than max_age_days."""
    if not queue_dir.exists():
        return

    now = time.time()
    max_age_seconds = max_age_days * 24 * 3600

    for f in queue_dir.glob("*.json"):
        try:
            if now - f.stat().st_mtime > max_age_seconds:
                f.unlink()
        except Exception:
            pass


def main():
    """Main entry point."""
    try:
        # Read hook input (required even if not used)
        sys.stdin.read()

        helix_dir = get_helix_dir()
        queue_dir = helix_dir / "learning-queue"
        log_file = helix_dir / "session.log"

        # Count pending items
        pending_count = count_pending_items(queue_dir)

        # Log session end
        log_event(log_file, "SESSION_END", f"pending_queue={pending_count}")

        # Log pending item details
        if pending_count > 0:
            log_event(log_file, "INFO", f"{pending_count} learning candidates pending review")
            log_pending_details(queue_dir, log_file)

        # Cleanup old queue files
        cleanup_old_files(queue_dir)

        # Always output valid JSON
        print("{}")

    except Exception as e:
        # Log error but never crash
        try:
            helix_dir = Path.cwd() / ".helix"
            log_file = helix_dir / "session.log"
            log_event(log_file, "ERROR", "session_end", str(e))
        except Exception:
            pass
        print("{}")


if __name__ == "__main__":
    main()
