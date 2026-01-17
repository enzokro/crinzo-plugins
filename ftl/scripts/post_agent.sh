#!/bin/bash
# FTL v2: Post-agent hook with race condition prevention
# Runs after any agent completes

AGENT_NAME="${1:-unknown}"
WORKSPACE_ID="${2:-}"  # Optional: workspace ID from agent output

# Ensure cache directory exists
mkdir -p .ftl/cache

# Log agent completion
echo "$(date -Iseconds) $AGENT_NAME" >> .ftl/cache/agent.log

# If workspace ID provided, use it directly (avoids race condition)
if [ -n "$WORKSPACE_ID" ]; then
    WORKSPACE_FILE=".ftl/workspace/${WORKSPACE_ID}_complete.xml"
    if [ ! -f "$WORKSPACE_FILE" ]; then
        WORKSPACE_FILE=".ftl/workspace/${WORKSPACE_ID}_blocked.xml"
    fi
    if [ ! -f "$WORKSPACE_FILE" ]; then
        WORKSPACE_FILE=".ftl/workspace/${WORKSPACE_ID}_active.xml"
    fi

    if [ -f "$WORKSPACE_FILE" ]; then
        python3 "${CLAUDE_PLUGIN_ROOT}/lib/workspace.py" parse "$WORKSPACE_FILE" > .ftl/cache/last_workspace.json 2>/dev/null
        exit 0
    fi
fi

# Fallback: find most recently modified workspace
# Note: This has a race condition if multiple workspaces are modified simultaneously
LATEST_WS=""
LATEST_MTIME=0

for f in .ftl/workspace/*_complete.xml .ftl/workspace/*_blocked.xml .ftl/workspace/*_active.xml 2>/dev/null; do
    if [ -f "$f" ]; then
        MTIME=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null)
        if [ "$MTIME" -gt "$LATEST_MTIME" ]; then
            LATEST_MTIME=$MTIME
            LATEST_WS=$f
        fi
    fi
done

if [ -n "$LATEST_WS" ] && [ -f "$LATEST_WS" ]; then
    python3 "${CLAUDE_PLUGIN_ROOT}/lib/workspace.py" parse "$LATEST_WS" > .ftl/cache/last_workspace.json 2>/dev/null
fi
