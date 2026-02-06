#!/usr/bin/env python3
"""SessionEnd hook - log session summary.

Triggered by: SessionEnd lifecycle event

Logs SESSION_END event to .helix/session.log for diagnostics.
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

        # Log session end
        log_event(log_file, "SESSION_END")

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
