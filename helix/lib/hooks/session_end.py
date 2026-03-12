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
        (helix_dir / "recall_synthesis.json").unlink(missing_ok=True)
        (helix_dir / "session_checkpoint.md").unlink(missing_ok=True)

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

        # 2b. Cross-session synthesis (best-effort)
        synthesized = 0
        try:
            from memory.synthesis import synthesize_session
            from memory.core import store as _store, feedback as _feedback
            candidates = synthesize_session()
            for c in candidates:
                if c["type"] == "new":
                    r = _store(c["content"], tags=c["tags"], initial_effectiveness=0.45)
                    if r.get("status") in ("added", "merged"):
                        synthesized += 1
                elif c["type"] == "reinforcement" and c.get("existing_name"):
                    _feedback([c["existing_name"]], "delivered",
                              causal_names=[(c["existing_name"], 0.80)])
                    synthesized += 1
        except Exception:
            pass

        # 3. Log session summary
        log_event(log_file, "SESSION_END", f"decayed={decayed}", f"pruned={pruned}", f"orphans={orphans}", f"synthesized={synthesized}")

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
