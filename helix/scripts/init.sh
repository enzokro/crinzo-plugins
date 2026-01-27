#!/bin/bash
# Helix initialization - heavy one-time setup operations
# Triggered by: claude --init, --init-only, --maintenance, or auto-heal from setup-env.sh
set -e
set -o pipefail

# Resolve HELIX_ROOT
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    HELIX_ROOT="$CLAUDE_PLUGIN_ROOT"
elif [ -f ".helix/plugin_root" ]; then
    HELIX_ROOT="$(cat .helix/plugin_root)"
else
    HELIX_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
export HELIX_ROOT
export CLAUDE_PLUGIN_ROOT="$HELIX_ROOT"

VENV_PATH="$HELIX_ROOT/.venv"
REQUIREMENTS="$HELIX_ROOT/requirements.txt"

# Create or recreate venv
create_venv() {
    echo "[helix] Creating virtual environment..."
    python3 -m venv "$VENV_PATH"

    echo "[helix] Installing dependencies..."
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
    echo "[helix] Dependencies installed"
}

# Main initialization logic (idempotent)
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

# Initialize database
echo "[helix] Initializing database..."
"$VENV_PATH/bin/python3" "$HELIX_ROOT/lib/db/connection.py" 2>/dev/null || true

# Verify installation
if "$VENV_PATH/bin/python3" -c "import sentence_transformers" 2>/dev/null; then
    echo "[helix] Initialization complete (sentence-transformers ready)"
else
    echo "[helix] WARNING: sentence-transformers import failed"
    exit 1
fi
