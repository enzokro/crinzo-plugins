#!/bin/bash
# Helix environment setup - creates venv and installs dependencies on first session
set -e
set -o pipefail

# Unified path resolution: CLAUDE_PLUGIN_ROOT is source of truth
# Both HELIX_ROOT and CLAUDE_PLUGIN_ROOT are set for backwards compatibility
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    HELIX_ROOT="$CLAUDE_PLUGIN_ROOT"
elif [ -f ".helix/plugin_root" ]; then
    # Fallback to cached plugin_root if available
    HELIX_ROOT="$(cat .helix/plugin_root)"
else
    HELIX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
# Ensure both variables are set consistently
export CLAUDE_PLUGIN_ROOT="$HELIX_ROOT"
export HELIX_ROOT

# CRITICAL: Persist plugin root for sub-agents
# Sub-agents spawned via Task tool do NOT inherit environment variables.
# Writing to .helix/plugin_root allows sub-agents to locate the plugin via:
#   $(cat .helix/plugin_root)
mkdir -p .helix
echo "$HELIX_ROOT" > .helix/plugin_root

VENV_PATH="$HELIX_ROOT/venv"
REQUIREMENTS="$HELIX_ROOT/requirements.txt"

# Create venv and install dependencies (only once)
if [ ! -d "$VENV_PATH" ]; then
    echo "[helix] Creating virtual environment..."
    python3 -m venv "$VENV_PATH"

    echo "[helix] Installing dependencies..."
    # Upgrade pip: quiet but show errors
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true

    # Install requirements: quiet progress bar but show errors
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1

    echo "[helix] Environment ready (sentence-transformers installed)"
fi

# Validate venv integrity (directory exists != functional)
if [ ! -x "$VENV_PATH/bin/python3" ]; then
    echo "[helix] ERROR: venv corrupted (python3 not executable), recreating..."
    rm -rf "$VENV_PATH"
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
    echo "[helix] Environment recreated"
fi

# Persist environment for Claude's subsequent bash commands
# PYTHONPATH enables sub-agents to import lib modules from any working directory
# NOTE: Expand $PATH and $PYTHONPATH at write time to avoid shell escaping issues
if [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH='$VENV_PATH/bin:$PATH'" >> "$CLAUDE_ENV_FILE"
    echo "export PYTHONPATH='$HELIX_ROOT:$PYTHONPATH'" >> "$CLAUDE_ENV_FILE"
    echo "export HELIX_ROOT='$HELIX_ROOT'" >> "$CLAUDE_ENV_FILE"
    echo "export HELIX_PLUGIN_ROOT='$HELIX_ROOT'" >> "$CLAUDE_ENV_FILE"
fi

# Initialize database
"$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/db/connection.py" 2>/dev/null || true

# Check memory health
HEALTH=$("$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/memory/core.py" health 2>/dev/null || echo '{"status":"INIT","total":0}')
STATUS=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','INIT'))" 2>/dev/null || echo "INIT")
TOTAL=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))" 2>/dev/null || echo "0")

echo "[helix] Ready. Memory: $STATUS ($TOTAL entries)"
