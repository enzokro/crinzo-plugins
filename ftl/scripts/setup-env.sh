#!/bin/bash
# FTL environment setup - creates venv and installs dependencies on first session
set -e

# Use CLAUDE_PLUGIN_ROOT if available, otherwise derive from script location
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    FTL_ROOT="$CLAUDE_PLUGIN_ROOT"
else
    FTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

VENV_PATH="$FTL_ROOT/venv"
REQUIREMENTS="$FTL_ROOT/requirements.txt"

# Create venv and install dependencies (only once)
if [ ! -d "$VENV_PATH" ]; then
    echo "[ftl] Creating virtual environment..."
    python3 -m venv "$VENV_PATH"

    echo "[ftl] Installing dependencies..."
    # Upgrade pip: quiet but show errors
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true

    # Install requirements: quiet progress bar but show errors
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1

    echo "[ftl] Environment ready (sentence-transformers installed)"
fi

# Validate venv integrity (directory exists != functional)
if [ ! -x "$VENV_PATH/bin/python3" ]; then
    echo "[ftl] ERROR: venv corrupted (python3 not executable), recreating..."
    rm -rf "$VENV_PATH"
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip --quiet --progress-bar off 2>&1 | grep -v "already satisfied" || true
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
    echo "[ftl] Environment recreated"
fi

# Quick sanity check: can we import the embeddings module?
if ! "$VENV_PATH/bin/python3" -c "import sentence_transformers" 2>/dev/null; then
    echo "[ftl] WARNING: sentence-transformers not importable, reinstalling..."
    "$VENV_PATH/bin/pip" install -r "$REQUIREMENTS" --progress-bar off 2>&1
fi

# Persist environment for Claude's subsequent bash commands
if [ -n "$CLAUDE_ENV_FILE" ]; then
    # Export paths so all ftl Python scripts use the venv
    echo "export FTL_ROOT='$FTL_ROOT'" >> "$CLAUDE_ENV_FILE"
    echo "export FTL_VENV='$VENV_PATH'" >> "$CLAUDE_ENV_FILE"
    echo "export PATH='$VENV_PATH/bin:\$PATH'" >> "$CLAUDE_ENV_FILE"
fi

exit 0
