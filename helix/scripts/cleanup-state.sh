#!/bin/bash
# Clean up stale helix state files
#
# Removes:
# - injection-state files older than 24 hours
#
# Called from setup-env.sh on session start
# Note: setup-env.sh already rm -rf's injection-state/ on each session.
# This handles the edge case of stale files from interrupted sessions.

set -euo pipefail

HELIX_DIR="${HELIX_PROJECT_DIR:-.}/.helix"

# Skip if no .helix directory
if [ ! -d "$HELIX_DIR" ]; then
    exit 0
fi

CLEANED=0

# Clean stale injection-state files (older than 24 hours)
INJECTION_DIR="$HELIX_DIR/injection-state"
if [ -d "$INJECTION_DIR" ]; then
    COUNT=$(find "$INJECTION_DIR" -type f -mtime +1 2>/dev/null | wc -l | tr -d ' ')
    if [ "$COUNT" -gt 0 ]; then
        find "$INJECTION_DIR" -type f -mtime +1 -delete 2>/dev/null || true
        CLEANED=$((CLEANED + COUNT))
    fi
fi

# Report if anything was cleaned
if [ "$CLEANED" -gt 0 ]; then
    echo "[helix] Cleaned $CLEANED stale state files"
fi
