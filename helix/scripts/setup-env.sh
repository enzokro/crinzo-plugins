#!/bin/bash
# Helix session startup - fast env persistence and health check
# Heavy operations delegated to init.sh (Setup hook or self-heal)
set -e
set -o pipefail

# Resolve HELIX_ROOT: CLAUDE_PLUGIN_ROOT is source of truth
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    HELIX_ROOT="$CLAUDE_PLUGIN_ROOT"
elif [ -f ".helix/plugin_root" ]; then
    HELIX_ROOT="$(cat .helix/plugin_root)"
else
    HELIX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
export HELIX_ROOT
export CLAUDE_PLUGIN_ROOT="$HELIX_ROOT"

# Persist plugin root for sub-agents (they don't inherit env vars)
mkdir -p .helix
echo "$HELIX_ROOT" > .helix/plugin_root

VENV_PATH="$HELIX_ROOT/.venv"

# Self-heal: trigger init if venv missing or corrupted
if [ ! -d "$VENV_PATH" ] || [ ! -x "$VENV_PATH/bin/python3" ]; then
    echo "[helix] venv missing or corrupted, initializing..."
    source "$HELIX_ROOT/scripts/init.sh"
fi

# Persist environment for Claude's bash commands
# PYTHONPATH enables sub-agents to import lib modules from any working directory
# HELIX_DB_PATH ensures subprocesses from different CWDs hit the same database
PROJECT_ROOT="$(pwd)"
HELIX_DB_PATH="$PROJECT_ROOT/.helix/helix.db"
export HELIX_DB_PATH

if [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH='$VENV_PATH/bin:$PATH'" >> "$CLAUDE_ENV_FILE"
    echo "export PYTHONPATH='$HELIX_ROOT:$PYTHONPATH'" >> "$CLAUDE_ENV_FILE"
    echo "export HELIX_ROOT='$HELIX_ROOT'" >> "$CLAUDE_ENV_FILE"
    echo "export HELIX_DB_PATH='$HELIX_DB_PATH'" >> "$CLAUDE_ENV_FILE"
fi

# Quick health check
HEALTH=$("$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/memory/core.py" health 2>/dev/null || echo '{"status":"INIT","total":0}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','INIT'))" 2>/dev/null || echo "INIT")
TOTAL=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo "0")

echo "[helix] Ready. Memory: $STATUS ($TOTAL entries)"
