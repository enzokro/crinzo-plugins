#!/bin/bash
# PostToolUse hook for Task - fallback extraction if SubagentStop doesn't fire
#
# Reads hook input from stdin, checks if it's a completed helix agent Task,
# and triggers learning extraction from the returned transcript.
#
# Returns:
#   {} - always (side effects only)

set -euo pipefail

# Get helix root from environment or script location
HELIX_ROOT="${HELIX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Read input from stdin
INPUT=$(cat)

# Log all PostToolUse(Task) events for diagnostics
LOG_DIR="${PWD}/.helix/hook-trace"
mkdir -p "$LOG_DIR"
echo "$INPUT" > "$LOG_DIR/posttool-task-$(date +%s).json"

# Quick check: is this a Task tool call?
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
if [ "$TOOL_NAME" != "Task" ]; then
    echo "{}"
    exit 0
fi

# Quick check: is this a helix agent?
SUBAGENT_TYPE=$(echo "$INPUT" | jq -r '.tool_input.subagent_type // ""')
case "$SUBAGENT_TYPE" in
    helix:helix-*)
        ;;
    *)
        echo "{}"
        exit 0
        ;;
esac

# Get agent_id from tool_result (if available)
AGENT_ID=$(echo "$INPUT" | jq -r '.tool_result.agent_id // ""')
if [ -z "$AGENT_ID" ]; then
    echo "{}"
    exit 0
fi

# Check if we already processed this agent via SubagentStop
QUEUE_DIR="${PWD}/.helix/learning-queue"
if [ -f "$QUEUE_DIR/${AGENT_ID}.json" ]; then
    # Already processed by SubagentStop - no need for fallback
    echo "{}"
    exit 0
fi

# Try to find the transcript path
# Claude Code stores transcripts at: ~/.claude/projects/{project}/{session}/subagents/agent-{id}.jsonl
# We need to search for it or get it from tool_result
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.tool_result.output_file // ""')

if [ -z "$TRANSCRIPT_PATH" ]; then
    # Fallback: try common locations
    CLAUDE_DIR="${HOME}/.claude"
    if [ -d "$CLAUDE_DIR" ]; then
        # Find most recent transcript matching agent_id
        TRANSCRIPT_PATH=$(find "$CLAUDE_DIR" -name "agent-${AGENT_ID}.jsonl" -type f 2>/dev/null | head -1)
    fi
fi

if [ -z "$TRANSCRIPT_PATH" ] || [ ! -f "$TRANSCRIPT_PATH" ]; then
    # Log that we couldn't find transcript
    echo "$(date -Iseconds) | FALLBACK | no_transcript | $SUBAGENT_TYPE | $AGENT_ID" >> "${PWD}/.helix/extraction.log"
    echo "{}"
    exit 0
fi

# Construct hook input for extract_learning.py
EXTRACT_INPUT=$(jq -n \
    --arg agent_id "$AGENT_ID" \
    --arg agent_type "$SUBAGENT_TYPE" \
    --arg transcript_path "$TRANSCRIPT_PATH" \
    '{agent_id: $agent_id, agent_type: $agent_type, agent_transcript_path: $transcript_path}')

# Process with Python extractor
echo "$EXTRACT_INPUT" | python3 "$HELIX_ROOT/lib/hooks/extract_learning.py"
