#!/bin/bash
# Helix session startup - env persistence, venv management, and health check
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

# Wipe ephemeral session state (coordination artifacts, not insights)
rm -f .helix/task-status.jsonl
rm -rf .helix/explorer-results/

VENV_PATH="$HELIX_ROOT/.venv"
REQUIREMENTS="$HELIX_ROOT/requirements.txt"

# Inline venv management (was init.sh — kept as standalone for manual --init)
create_venv() {
    echo "[helix] Creating virtual environment..."
    python3 -m venv "$VENV_PATH"
    echo "[helix] Installing dependencies..."
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
    echo "[helix] Dependencies installed"
}

if [ ! -d "$VENV_PATH" ]; then
    create_venv
elif [ ! -x "$VENV_PATH/bin/python3" ]; then
    echo "[helix] venv corrupted (python3 not executable), recreating..."
    rm -rf "$VENV_PATH"
    create_venv
else
    # Venv exists and is valid - check if requirements changed
    if [ -f "$REQUIREMENTS" ] && [ "$REQUIREMENTS" -nt "$VENV_PATH" ]; then
        echo "[helix] Requirements updated, syncing dependencies..."
        "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
        touch "$VENV_PATH"
    else
        echo "[helix] venv already initialized"
    fi
fi

# Verify installation
if ! "$VENV_PATH/bin/python3" -c "import sentence_transformers" 2>/dev/null; then
    echo "[helix] WARNING: sentence-transformers import failed"
    exit 1
fi
echo "[helix] Initialization complete (sentence-transformers ready)"

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
    echo "export HELIX_PROJECT_DIR='$PROJECT_ROOT'" >> "$CLAUDE_ENV_FILE"
fi

# Quick health check (single python3 -c for both fields)
HEALTH=$("$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/memory/core.py" health 2>/dev/null || echo '{"status":"INIT","total_insights":0}')
read STATUS TOTAL <<< $("$VENV_PATH/bin/python3" -c "
import sys,json; d=json.load(sys.stdin)
print(d.get('status','INIT'), d.get('total_insights',0))
" <<< "$HEALTH" 2>/dev/null || echo "INIT 0")

# Background warmup: prime OS page cache with embedding model files
# By the time the orchestrator needs inject_context (after planning phase),
# the model files are already in memory, eliminating disk I/O latency.
"$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/memory/embeddings.py" warmup >/dev/null 2>&1 &

echo "[helix] Ready. Memory: $STATUS ($TOTAL entries)"
