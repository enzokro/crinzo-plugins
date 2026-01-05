#!/usr/bin/env python3
"""
inject_context.py - Inject cached Delta contents into agent context

Runs via UserPromptSubmit hook before Builder or Learner processes prompt.
Returns additionalContext with pre-loaded file contents to avoid re-reads.

Flow:
  Builder receives: pre-edit Delta files (cached after Router)
  Learner receives: post-edit Delta files (cached after Builder)
"""
import json
import sys
from pathlib import Path

CACHE_FILE = Path(".ftl/cache/delta_contents.md")


def main():
    # No cache = nothing to inject
    if not CACHE_FILE.exists():
        sys.exit(0)

    contents = CACHE_FILE.read_text()
    if not contents.strip():
        sys.exit(0)

    # Build additionalContext injection
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": f"""## Pre-loaded Delta Contents

These Delta files were cached from the previous agent's completion.
DO NOT re-read these files—use the contents below.

{contents}
"""
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
