#!/bin/bash
# Lattice v2: Setup semantic memory dependencies
# Runs on SessionStart. Silent, idempotent, graceful.

set -e

# Check if already installed (fast path)
if python3 -c "import sentence_transformers" 2>/dev/null; then
    exit 0
fi

# Install dependencies silently
PLUGIN_DIR="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"

if [ -f "$PLUGIN_DIR/requirements.txt" ]; then
    pip install -q --user -r "$PLUGIN_DIR/requirements.txt" 2>/dev/null || true
fi

exit 0
