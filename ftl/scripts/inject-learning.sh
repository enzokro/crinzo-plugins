#!/bin/bash
# Mid-campaign learning injection hook
# Triggers when a workspace is blocked, immediately extracts failure to memory
set -e
set -o pipefail

# Read hook input from stdin
INPUT=$(cat)

# Extract workspace path from tool result (looks for _blocked.xml in output)
# This hook fires after Write/Edit tools complete
RESULT=$(echo "$INPUT" | jq -r '.result // empty' 2>/dev/null)

# Check if result mentions a blocked workspace
if [[ ! "$RESULT" == *"_blocked.xml"* ]]; then
    exit 0
fi

# Extract the blocked workspace path from the result
WORKSPACE=$(echo "$RESULT" | grep -oE '[^ ]*_blocked\.xml' | head -1)

if [ -z "$WORKSPACE" ] || [ ! -f "$WORKSPACE" ]; then
    exit 0
fi

# Resolve FTL root
FTL_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cat .ftl/plugin_root 2>/dev/null || echo "")}"
if [ -z "$FTL_ROOT" ] || [ ! -d "$FTL_ROOT" ]; then
    exit 0
fi

# Extract failure from blocked workspace using existing observer function
FAILURE_JSON=$("$FTL_ROOT/venv/bin/python3" "$FTL_ROOT/lib/observer.py" extract-failure "$WORKSPACE" 2>/dev/null || echo "")

if [ -n "$FAILURE_JSON" ] && [ "$FAILURE_JSON" != "null" ] && [ "$FAILURE_JSON" != "{}" ]; then
    # Add to memory immediately (atomic operation)
    echo "$FAILURE_JSON" | "$FTL_ROOT/venv/bin/python3" "$FTL_ROOT/lib/memory.py" add-failure --json - 2>/dev/null || true
    echo "[ftl] Mid-campaign learning: injected failure from $(basename "$WORKSPACE")"
fi

exit 0
