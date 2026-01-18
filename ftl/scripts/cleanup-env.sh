#!/bin/bash
# FTL session cleanup - logs session end and cleans transient files
set -e
set -o pipefail

# Read input from stdin (Claude hook input format)
INPUT=$(cat)
REASON=$(echo "$INPUT" | jq -r '.reason // "unknown"')

# Ensure .ftl directory exists for logging
FTL_DIR="$HOME/.ftl"
mkdir -p "$FTL_DIR"

# Log session end
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "[${TIMESTAMP}] Session ended (reason: $REASON)" >> "$FTL_DIR/sessions.log"

# Clean transient cache files (explorer outputs from current session)
CACHE_DIR=".ftl/cache"
if [ -d "$CACHE_DIR" ]; then
    rm -f "$CACHE_DIR"/explorer_*.json 2>/dev/null || true
fi

exit 0
