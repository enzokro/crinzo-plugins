#!/bin/bash
# Clean up stale helix state files
#
# Removes:
# - injection-state files older than 24 hours
# - hook-trace files older than 7 days
#
# Called from setup-env.sh on session start

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

# Clean old hook-trace files (older than 7 days)
TRACE_DIR="$HELIX_DIR/hook-trace"
if [ -d "$TRACE_DIR" ]; then
    COUNT=$(find "$TRACE_DIR" -type f -mtime +7 2>/dev/null | wc -l | tr -d ' ')
    if [ "$COUNT" -gt 0 ]; then
        find "$TRACE_DIR" -type f -mtime +7 -delete 2>/dev/null || true
        CLEANED=$((CLEANED + COUNT))
    fi
fi

# Report if anything was cleaned
if [ "$CLEANED" -gt 0 ]; then
    echo "[helix] Cleaned $CLEANED stale state files"
fi
