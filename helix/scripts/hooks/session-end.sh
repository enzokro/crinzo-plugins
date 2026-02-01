#!/bin/bash
# SessionEnd hook - processes remaining learning queue items
#
# Called when a Claude Code session ends. Checks for unprocessed
# learning candidates and logs summary.
#
# Returns:
#   {} - always (side effects only)

set -euo pipefail

# Get helix root from environment or script location
HELIX_ROOT="${HELIX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

HELIX_DIR="${PWD}/.helix"
QUEUE_DIR="$HELIX_DIR/learning-queue"
LOG_FILE="$HELIX_DIR/session.log"

# Ensure log directory exists
mkdir -p "$HELIX_DIR"

# Count pending queue items
PENDING_COUNT=0
if [ -d "$QUEUE_DIR" ]; then
    PENDING_COUNT=$(find "$QUEUE_DIR" -name "*.json" -type f 2>/dev/null | wc -l | tr -d ' ')
fi

# Log session end
TIMESTAMP=$(date -Iseconds)
echo "$TIMESTAMP | SESSION_END | pending_queue=$PENDING_COUNT" >> "$LOG_FILE"

if [ "$PENDING_COUNT" -gt 0 ]; then
    echo "$TIMESTAMP | INFO | $PENDING_COUNT learning candidates pending review" >> "$LOG_FILE"

    # List pending items
    if [ -d "$QUEUE_DIR" ]; then
        for f in "$QUEUE_DIR"/*.json; do
            if [ -f "$f" ]; then
                AGENT_ID=$(basename "$f" .json)
                CANDIDATE_COUNT=$(jq -r '.candidates | length' "$f" 2>/dev/null || echo "?")
                echo "$TIMESTAMP | PENDING | agent=$AGENT_ID | candidates=$CANDIDATE_COUNT" >> "$LOG_FILE"
            fi
        done
    fi
fi

# Auto-store medium-confidence candidates that match existing high-effectiveness patterns
# This closes the learning loop for candidates that are likely valuable
if [ "$PENDING_COUNT" -gt 0 ] && [ -x "$HELIX_ROOT/.venv/bin/python3" ]; then
    # Process each queue file
    for f in "$QUEUE_DIR"/*.json; do
        if [ -f "$f" ]; then
            AGENT_ID=$(basename "$f" .json)

            # Extract medium-confidence candidates
            MEDIUM_CANDIDATES=$(jq -c '[.candidates[] | select(.confidence == "medium")]' "$f" 2>/dev/null || echo "[]")

            if [ "$MEDIUM_CANDIDATES" != "[]" ]; then
                # For each medium confidence candidate, check if similar high-effectiveness memories exist
                echo "$MEDIUM_CANDIDATES" | jq -c '.[]' | while read -r candidate; do
                    TRIGGER=$(echo "$candidate" | jq -r '.trigger')
                    MEM_TYPE=$(echo "$candidate" | jq -r '.type')

                    # Query for similar existing memories with good effectiveness
                    SIMILAR=$("$HELIX_ROOT/.venv/bin/python3" "$HELIX_ROOT/lib/memory/core.py" similar-recent "$TRIGGER" --threshold 0.7 --type "$MEM_TYPE" 2>/dev/null || echo "[]")
                    SIMILAR_COUNT=$(echo "$SIMILAR" | jq 'length' 2>/dev/null || echo "0")

                    if [ "$SIMILAR_COUNT" -gt 0 ]; then
                        # Check if any similar memory has good effectiveness
                        HIGH_EFF=$(echo "$SIMILAR" | jq '[.[] | select(.effectiveness >= 0.6)] | length' 2>/dev/null || echo "0")

                        if [ "$HIGH_EFF" -gt 0 ]; then
                            # Auto-store - pattern matches existing successful memories
                            RESOLUTION=$(echo "$candidate" | jq -r '.resolution')
                            SOURCE=$(echo "$candidate" | jq -r '.source')

                            STORE_RESULT=$("$HELIX_ROOT/.venv/bin/python3" "$HELIX_ROOT/lib/memory/core.py" store \
                                --trigger "$TRIGGER" \
                                --resolution "$RESOLUTION" \
                                --type "$MEM_TYPE" \
                                --source "session-end:$SOURCE:$AGENT_ID" 2>&1 || echo '{"status":"error"}')

                            echo "$TIMESTAMP | AUTO_STORE | agent=$AGENT_ID | type=$MEM_TYPE | result=$STORE_RESULT" >> "$LOG_FILE"
                        fi
                    fi
                done
            fi
        fi
    done
fi

# Clean up old queue files (older than 7 days)
if [ -d "$QUEUE_DIR" ]; then
    find "$QUEUE_DIR" -name "*.json" -type f -mtime +7 -delete 2>/dev/null || true
fi

echo "{}"
