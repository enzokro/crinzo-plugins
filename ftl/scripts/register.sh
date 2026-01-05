#!/bin/bash
# Register FTL library path
# Called by SessionStart hook. CLAUDE_PLUGIN_ROOT is available in hooks.

set -e

PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(dirname "$(dirname "$0")")}"

mkdir -p ~/.config/ftl
REGISTRY=~/.config/ftl/paths.sh

# Single FTL_LIB export (replaces TETHER_LIB, LATTICE_LIB, FORGE_LIB)
echo "export FTL_LIB=\"$PLUGIN_ROOT/lib\"" > "$REGISTRY"

exit 0
