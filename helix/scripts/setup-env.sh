#!/bin/bash
# Helix SessionStart hook - initialize environment

set -e

# Create helix directory
mkdir -p .helix

# Store plugin root for CLI access
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "$CLAUDE_PLUGIN_ROOT" > .helix/plugin_root
fi

# Initialize database (creates tables if not exists)
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    python3 "$CLAUDE_PLUGIN_ROOT/lib/db/connection.py" 2>/dev/null || true
fi

# Log session start
echo "$(date -Iseconds) session_start" >> .helix/sessions.log 2>/dev/null || true

echo "Helix initialized"
