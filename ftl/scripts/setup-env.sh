#!/bin/bash
# FTL environment setup - creates venv and installs dependencies on first session
set -e

# Unified path resolution: CLAUDE_PLUGIN_ROOT is source of truth
# Both FTL_ROOT and CLAUDE_PLUGIN_ROOT are set for backwards compatibility
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    FTL_ROOT="$CLAUDE_PLUGIN_ROOT"
elif [ -f ".ftl/plugin_root" ]; then
    # Fallback to cached plugin_root if available
    FTL_ROOT="$(cat .ftl/plugin_root)"
else
    FTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
# Ensure both variables are set consistently
export CLAUDE_PLUGIN_ROOT="$FTL_ROOT"
export FTL_ROOT

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

# Persist environment for Claude's subsequent bash commands
if [ -n "$CLAUDE_ENV_FILE" ]; then
    echo "export PATH='$VENV_PATH/bin:$PATH'" >> "$CLAUDE_ENV_FILE"
fi
