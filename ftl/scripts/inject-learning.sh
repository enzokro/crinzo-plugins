#!/bin/bash
# Mid-campaign learning injection hook
# Triggers when a workspace is blocked, immediately extracts failure to memory
set -e
set -o pipefail

# Read hook input from stdin
INPUT=$(cat)

# Extract workspace ID from tool result (looks for workspace blocking operations)
# This hook fires after workspace.py block command completes
RESULT=$(echo "$INPUT" | jq -r '.result // empty' 2>/dev/null)

# Check if result mentions a blocked workspace (new format or legacy XML format)
if [[ ! "$RESULT" == *"blocked"* ]] && [[ ! "$RESULT" == *"_blocked.xml"* ]]; then
    exit 0
fi

# Extract workspace ID from the result
# Pattern: "NNN-slug" format from database operations
WORKSPACE_ID=$(echo "$RESULT" | grep -oE '[0-9]{3}-[a-z0-9-]+' | head -1)

if [ -z "$WORKSPACE_ID" ]; then
    # Try extracting from JSON format
    WORKSPACE_ID=$(echo "$RESULT" | jq -r '.workspace_id // empty' 2>/dev/null)
fi

if [ -z "$WORKSPACE_ID" ]; then
    # Legacy: try extracting from XML path format
    WORKSPACE_ID=$(echo "$RESULT" | grep -oE '[0-9]{3}_[a-z0-9_-]+_blocked' | head -1 | sed 's/_blocked$//' | tr '_' '-')
fi

if [ -z "$WORKSPACE_ID" ]; then
    exit 0
fi

# Resolve FTL root
FTL_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cat .ftl/plugin_root 2>/dev/null || echo "")}"
if [ -z "$FTL_ROOT" ] || [ ! -d "$FTL_ROOT" ]; then
    exit 0
fi

# Extract failure from blocked workspace using existing observer function
FAILURE_JSON=$("$FTL_ROOT/venv/bin/python3" "$FTL_ROOT/lib/observer.py" extract-failure "$WORKSPACE_ID" 2>/dev/null || echo "")

if [ -n "$FAILURE_JSON" ] && [ "$FAILURE_JSON" != "null" ] && [ "$FAILURE_JSON" != "{}" ]; then
    # Add to memory immediately (atomic operation)
    # Pass JSON directly as argument (stdin '-' not supported by CLI)
    "$FTL_ROOT/venv/bin/python3" "$FTL_ROOT/lib/memory.py" add-failure --json "$FAILURE_JSON" 2>/dev/null || true
    echo "[ftl] Mid-campaign learning: injected failure from $WORKSPACE_ID"
fi

exit 0
