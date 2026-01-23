#!/bin/bash
# Helix session initialization
set -e

mkdir -p .helix

# Store plugin root for sub-agent and hook access
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "$CLAUDE_PLUGIN_ROOT" > .helix/plugin_root
fi

# Persist environment for Claude's bash commands
if [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export HELIX_PLUGIN_ROOT=\"$CLAUDE_PLUGIN_ROOT\"" >> "$CLAUDE_ENV_FILE"
    echo "export HELIX_DB=\"$CLAUDE_PROJECT_DIR/.helix/helix.db\"" >> "$CLAUDE_ENV_FILE"
fi

# Initialize database
python3 "$CLAUDE_PLUGIN_ROOT/lib/db/connection.py" 2>/dev/null || true

# Check memory health
HEALTH=$(python3 "$CLAUDE_PLUGIN_ROOT/lib/memory/core.py" health 2>/dev/null || echo '{"status":"INIT"}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','INIT'))" 2>/dev/null || echo "INIT")
TOTAL=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo "0")

echo "Helix ready. Memory: $STATUS ($TOTAL entries)"
