#!/usr/bin/env python3
"""SessionEnd hook - clean up session state and run maintenance.

Triggered by: SessionEnd lifecycle event

Actions:
1. Clean injection-state (prevent cross-session collision)
2. Remove task-status.jsonl (append-only, never cleaned)
3. Run decay on dormant insights
4. Log session summary
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from paths import get_helix_dir


def log_event(log_file: Path, *parts):
    """Append log entry."""
    ts = datetime.now(timezone.utc).isoformat()
    log_file.parent.mkdir(exist_ok=True)
    with open(log_file, 'a') as f:
        f.write(f"{ts} | " + " | ".join(str(p) for p in parts) + "\n")


def main():
    """Main entry point."""
    try:
        # Read hook input (required even if not used)
        sys.stdin.read()

        helix_dir = get_helix_dir()
        log_file = helix_dir / "session.log"

        # 1. Clean injection-state (prevent cross-session collision)
        injection_dir = helix_dir / "injection-state"
        if injection_dir.exists():
            import shutil
            shutil.rmtree(injection_dir, ignore_errors=True)

        # 2. Truncate task-status.jsonl (append-only, never cleaned)
        status_file = helix_dir / "task-status.jsonl"
        if status_file.exists():
            status_file.unlink()

        # 3. Run decay on dormant insights
        try:
            from memory.core import decay
            decay_result = decay()
            decayed = decay_result.get("decayed", 0)
        except Exception:
            decayed = 0

        # 4. Log session summary
        log_event(log_file, "SESSION_END", f"decayed={decayed}")

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
