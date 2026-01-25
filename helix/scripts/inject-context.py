#!/usr/bin/env python3
"""PreToolUse hook for logging Edit/Write operations.

Context injection is handled by build_context() at task start.
This hook only logs file operations for debugging and audit purposes.

Keep this hook for:
1. Debugging file operations during development
2. Audit trail of modifications during builds
"""
import json
import sys
from pathlib import Path
from datetime import datetime


def log(status: str, file_path: str, details: str):
    """Append log entry to .helix/hook.log"""
    log_path = Path.cwd() / ".helix" / "hook.log"
    try:
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "a") as f:
            timestamp = datetime.now().isoformat()
            f.write(f"{timestamp} | {status} | {file_path} | {details}\n")
    except Exception:
        pass  # Don't fail if logging fails


def main():
    # Read hook input
    try:
        hook_input = json.load(sys.stdin)
    except Exception as e:
        log("FAIL", "N/A", f"Invalid JSON input: {e}")
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only process Edit/Write
    if tool_name not in ["Edit", "Write"]:
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        log("SKIP", "N/A", "No file_path in tool_input")
        sys.exit(0)

    # Log the operation
    log("OK", file_path, f"Tool: {tool_name}")

    # No output = no modification to tool behavior
    sys.exit(0)


if __name__ == "__main__":
    main()
