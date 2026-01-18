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

# Database cleanup is handled automatically by SQLite
# No transient cache files to clean (all explorer data in database)

exit 0
