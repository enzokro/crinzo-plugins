#!/usr/bin/env python3
"""PreToolUse hook for logging Edit/Write operations.

Context injection is now handled by build_context() at task start.
This hook only logs file operations for debugging and audit purposes.

The dual-path injection (build_prompt + hook) has been unified:
- OLD: Hook queries memory, injects context, tracks in separate file
- NEW: build_context() does all injection at task start, single tracking location

This hook is kept for:
1. Logging file operations for debugging
2. Potential future delta enforcement (checking files are in delta)
"""
import json
import sys
import os
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
    # Context injection is handled by build_context() at task start
    sys.exit(0)


if __name__ == "__main__":
    main()
