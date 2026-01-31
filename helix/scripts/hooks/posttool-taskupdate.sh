#!/bin/bash
# PostToolUse hook for TaskUpdate - auto-credits memories on task outcome
#
# Reads hook input from stdin, checks for helix_outcome in metadata,
# and automatically credits/debits injected memories based on outcome.
#
# Returns:
#   {} - always (side effects only)

set -euo pipefail

# Get helix root from environment or script location
HELIX_ROOT="${HELIX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Read input from stdin
INPUT=$(cat)

# Quick check: is this a TaskUpdate call?
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
if [ "$TOOL_NAME" != "TaskUpdate" ]; then
    echo "{}"
    exit 0
fi

# Check for helix outcome in metadata
HELIX_OUTCOME=$(echo "$INPUT" | jq -r '.tool_input.metadata.helix_outcome // ""')
if [ -z "$HELIX_OUTCOME" ]; then
    echo "{}"
    exit 0
fi

TASK_ID=$(echo "$INPUT" | jq -r '.tool_input.taskId // ""')
if [ -z "$TASK_ID" ]; then
    echo "{}"
    exit 0
fi

# Find injection state for this task
HELIX_DIR="${PWD}/.helix"
INJECTION_DIR="$HELIX_DIR/injection-state"

if [ ! -d "$INJECTION_DIR" ]; then
    echo "{}"
    exit 0
fi

# Look for injection state matching this task_id
INJECTION_FILE=""
for f in "$INJECTION_DIR"/*.json; do
    if [ -f "$f" ]; then
        FILE_TASK_ID=$(jq -r '.task_id // ""' "$f")
        if [ "$FILE_TASK_ID" = "$TASK_ID" ]; then
            INJECTION_FILE="$f"
            break
        fi
    fi
done

if [ -z "$INJECTION_FILE" ] || [ ! -f "$INJECTION_FILE" ]; then
    echo "{}"
    exit 0
fi

# Get injected memories
INJECTED=$(jq -c '.injected_memories // []' "$INJECTION_FILE")

if [ "$INJECTED" = "[]" ]; then
    echo "{}"
    exit 0
fi

# Determine feedback delta based on outcome
case "$HELIX_OUTCOME" in
    delivered)
        DELTA="0.5"
        ;;
    blocked)
        DELTA="-0.3"
        ;;
    *)
        echo "{}"
        exit 0
        ;;
esac

# Credit/debit memories
python3 "$HELIX_ROOT/lib/memory/core.py" feedback --names "$INJECTED" --delta "$DELTA" >/dev/null 2>&1 || true

# Clean up injection state file
rm -f "$INJECTION_FILE"

echo "{}"
