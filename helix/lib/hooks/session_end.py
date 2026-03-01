#!/usr/bin/env python3
"""SessionEnd hook - clean up session state and run maintenance."""

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
        sys.stdin.read()

        helix_dir = get_helix_dir()
        log_file = helix_dir / "session.log"

        # 1. Remove task-status.jsonl
        (helix_dir / "task-status.jsonl").unlink(missing_ok=True)

        # 1b. Clean stale sideband files
        injected_dir = helix_dir / "injected"
        if injected_dir.exists():
            for f in injected_dir.iterdir():
                try:
                    f.unlink()
                except Exception:
                    pass

        # 2. Run decay + prune
        decayed = pruned = orphans = 0
        try:
            from memory.core import decay, prune
            decayed = decay().get("decayed", 0)
            prune_result = prune()
            pruned = prune_result.get("pruned", 0)
            orphans = prune_result.get("orphans_cleaned", 0)
        except Exception:
            pass

        # 3. Log session summary
        log_event(log_file, "SESSION_END", f"decayed={decayed}", f"pruned={pruned}", f"orphans={orphans}")

        print("{}")

    except Exception as e:
        try:
            helix_dir = Path.cwd() / ".helix"
            log_file = helix_dir / "session.log"
            log_event(log_file, "ERROR", "session_end", str(e))
        except Exception:
            pass
        print("{}")


if __name__ == "__main__":
    main()
