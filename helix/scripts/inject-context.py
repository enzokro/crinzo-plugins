#!/usr/bin/env python3
"""
PreToolUse hook that injects relevant memories before Edit/Write operations.
Returns additionalContext that Claude sees before executing the tool.

Direct memory import - no subprocess overhead.
"""
import json
import sys
import os
from pathlib import Path

# Add lib to path for direct import
lib_path = Path(__file__).parent.parent / "lib"
sys.path.insert(0, str(lib_path))


def main():
    # Read hook input
    try:
        hook_input = json.load(sys.stdin)
    except:
        sys.exit(0)

    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    # Only inject for Edit/Write
    if tool_name not in ["Edit", "Write"]:
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    try:
        # Direct import - no subprocess!
        from memory import recall

        # Query for relevant memories
        memories = recall(file_path, limit=3)

        if not memories:
            sys.exit(0)

        # Format memories as brief text for injection
        lines = []
        names = []
        for m in memories:
            eff = m.get("effectiveness", 0.5)
            mtype = m.get("type", "unknown")
            trigger = m.get("trigger", "")[:60]
            name = m.get("name", "")
            lines.append(f"- **{name}** [{mtype}] {trigger}... (eff: {eff:.0%})")
            names.append(name)

        brief = "\n".join(lines)
        names_str = ", ".join(names)

    except Exception:
        sys.exit(0)

    # Return additionalContext
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": (
                f"**Memories for {os.path.basename(file_path)}:**\n{brief}\n\n"
                f"Apply relevant patterns. Avoid listed failures.\n"
                f"When complete, report UTILIZED: [{names_str}] (only those that actually helped)"
            )
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
