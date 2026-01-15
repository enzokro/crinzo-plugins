#!/bin/bash
# FTL v2: Post-agent hook
# Runs after any agent completes

AGENT_NAME="${1:-unknown}"

# Ensure cache directory exists
mkdir -p .ftl/cache

# Log agent completion
echo "$(date -Iseconds) $AGENT_NAME" >> .ftl/cache/agent.log

# If workspace exists, cache last workspace info
LATEST_WS=$(ls -t .ftl/workspace/*_active.xml .ftl/workspace/*_complete.xml .ftl/workspace/*_blocked.xml 2>/dev/null | head -1)
if [ -n "$LATEST_WS" ] && [ -f "$LATEST_WS" ]; then
    python3 "${CLAUDE_PLUGIN_ROOT}/lib/workspace.py" parse "$LATEST_WS" > .ftl/cache/last_workspace.json 2>/dev/null
fi
