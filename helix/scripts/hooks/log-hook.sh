#!/bin/bash
# Universal hook logger - logs ALL hook events for diagnostics
#
# Usage: Add as first hook in any hook array to log input before processing
#   echo "$INPUT" | $HELIX_ROOT/scripts/hooks/log-hook.sh <hook-name>
#
# Output: .helix/hook-trace/<hook-name>_<timestamp>.json

HOOK_NAME="${1:-unknown}"

LOG_DIR="${PWD}/.helix/hook-trace"
mkdir -p "$LOG_DIR"

TIMESTAMP=$(date +%Y%m%dT%H%M%S%3N)
INPUT=$(cat)

# Log to file
echo "$INPUT" > "$LOG_DIR/${HOOK_NAME}_${TIMESTAMP}.json"

# Pass through for actual processing
echo "$INPUT"
