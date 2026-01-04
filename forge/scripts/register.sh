#!/bin/bash
# Register plugin path in FTL registry
# Called by SessionStart hook. CLAUDE_PLUGIN_ROOT is available in hooks.
# Usage: register.sh FORGE|TETHER|LATTICE

set -e

PLUGIN_NAME="$1"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"

mkdir -p ~/.config/ftl
REGISTRY=~/.config/ftl/paths.sh

# Atomic write: remove old entry for this plugin, append new
# Use plugin-specific temp file to avoid race conditions
TMP_FILE="$REGISTRY.tmp.$PLUGIN_NAME"
if [ -f "$REGISTRY" ]; then
    grep -v "^export ${PLUGIN_NAME}_LIB=" "$REGISTRY" > "$TMP_FILE" 2>/dev/null || true
else
    touch "$TMP_FILE"
fi

echo "export ${PLUGIN_NAME}_LIB=\"$PLUGIN_ROOT/lib\"" >> "$TMP_FILE"
mv "$TMP_FILE" "$REGISTRY"

exit 0
