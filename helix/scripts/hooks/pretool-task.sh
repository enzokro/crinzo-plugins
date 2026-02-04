#!/bin/bash
# PreToolUse hook for Task tool - injects memory context into helix agents
#
# Reads hook input from stdin, checks if it's a helix agent Task call,
# and enriches the prompt with memory context via inject_memory.py
#
# Returns:
#   {} - no modification (non-helix agents)
#   {"updatedInput": {...}} - modified prompt with memory context

set -euo pipefail

# Get helix root from environment or script location
HELIX_ROOT="${HELIX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Read input from stdin
INPUT=$(cat)

# Quick check: is this a Task tool call?
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
if [ "$TOOL_NAME" != "Task" ]; then
    echo "{}"
    exit 0
fi

# Quick check: is this a helix agent?
SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""')
case "$SUBAGENT_TYPE" in
    helix:helix-*)
        # Process with Python - let Python's ancestor search find the right .helix/
        # Only export if already set (inherited from CLAUDE_ENV_FILE)
        # Otherwise, Python's _get_default_db_path() walks up to find nearest .helix/
        [ -n "${HELIX_PROJECT_DIR:-}" ] && export HELIX_PROJECT_DIR
        [ -n "${HELIX_DB_PATH:-}" ] && export HELIX_DB_PATH
        echo "$INPUT" | python3 "$HELIX_ROOT/lib/hooks/inject_memory.py"
        ;;
    *)
        # Not a helix agent
        echo "{}"
        ;;
esac
