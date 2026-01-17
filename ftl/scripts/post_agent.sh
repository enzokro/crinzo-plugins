#!/bin/bash
# FTL v2: Post-agent hook with race condition prevention and structured errors
# Runs after any agent completes

set -e

AGENT_NAME="${1:-unknown}"
WORKSPACE_ID="${2:-}"  # Optional: workspace ID from agent output

# Validate CLAUDE_PLUGIN_ROOT before any Python calls
if [ -z "$CLAUDE_PLUGIN_ROOT" ]; then
    echo '{"error": "CLAUDE_PLUGIN_ROOT not set", "agent": "'"$AGENT_NAME"'"}' >&2
    exit 1
fi

if [ ! -f "$CLAUDE_PLUGIN_ROOT/lib/workspace.py" ]; then
    echo '{"error": "Invalid CLAUDE_PLUGIN_ROOT: workspace.py not found", "path": "'"$CLAUDE_PLUGIN_ROOT"'"}' >&2
    exit 1
fi

# Ensure cache directory exists
mkdir -p .ftl/cache

# JSON-safe string escaping (handles quotes, backslashes, newlines)
json_escape() {
    local str="$1"
    str="${str//\\/\\\\}"      # Backslashes first
    str="${str//\"/\\\"}"      # Double quotes
    str="${str//$'\n'/\\n}"    # Newlines
    str="${str//$'\t'/\\t}"    # Tabs
    str="${str//$'\r'/\\r}"    # Carriage returns
    printf '%s' "$str"
}

# Emit JSON object to stderr (keys passed as "key1" "val1" "key2" "val2" ...)
emit_json() {
    local output="{"
    local first=true
    while [ $# -ge 2 ]; do
        local key="$1"
        local val="$2"
        shift 2
        if [ "$first" = true ]; then
            first=false
        else
            output+=", "
        fi
        output+="\"$(json_escape "$key")\": \"$(json_escape "$val")\""
    done
    output+="}"
    printf '%s\n' "$output" >&2
}

# Structured error output
emit_error() {
    local exit_code="$1"
    local message="$2"
    emit_json "error" "$message" "agent" "$AGENT_NAME"
    exit "$exit_code"
}

# Parse workspace with atomic temp-file pattern
parse_workspace() {
    local ws_file="$1"
    local temp_file

    # Create temp file in same directory for atomic rename
    temp_file=$(mktemp .ftl/cache/.last_workspace.XXXXXX.json)

    if python3 "${CLAUDE_PLUGIN_ROOT}/lib/workspace.py" parse "$ws_file" > "$temp_file" 2>/dev/null; then
        # Atomic rename - prevents partial writes
        mv -f "$temp_file" .ftl/cache/last_workspace.json
        return 0
    else
        # Cleanup temp file on failure
        rm -f "$temp_file"
        return 1
    fi
}

# Log agent completion with timestamp
echo "$(date -Iseconds) $AGENT_NAME" >> .ftl/cache/agent.log

# If workspace ID provided, use it directly (avoids race condition)
if [ -n "$WORKSPACE_ID" ]; then
    # Try each status in priority order
    for status in complete blocked active; do
        WORKSPACE_FILE=".ftl/workspace/${WORKSPACE_ID}_${status}.xml"
        if [ -f "$WORKSPACE_FILE" ]; then
            if parse_workspace "$WORKSPACE_FILE"; then
                exit 0
            else
                emit_error 1 "Failed to parse workspace: ${WORKSPACE_FILE}"
            fi
        fi
    done

    # Workspace ID provided but no file found - warning, not error
    emit_json "warning" "workspace_not_found" "id" "$WORKSPACE_ID" "agent" "$AGENT_NAME"
fi

# Fallback: find most recently modified workspace
# WARNING: Race condition risk if multiple workspaces modified simultaneously
# Prefer explicit WORKSPACE_ID path above
if [ -z "$WORKSPACE_ID" ]; then
    emit_json "warning" "no_workspace_id" "agent" "$AGENT_NAME" "fallback" "mtime_scan"
fi

LATEST_WS=""
LATEST_MTIME=0

for f in .ftl/workspace/*_complete.xml .ftl/workspace/*_blocked.xml .ftl/workspace/*_active.xml; do
    if [ -f "$f" ]; then
        # Cross-platform mtime: try BSD stat first, then GNU stat
        MTIME=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null || echo 0)
        if [ "$MTIME" -gt "$LATEST_MTIME" ]; then
            LATEST_MTIME=$MTIME
            LATEST_WS=$f
        fi
    fi
done

if [ -n "$LATEST_WS" ] && [ -f "$LATEST_WS" ]; then
    if parse_workspace "$LATEST_WS"; then
        exit 0
    else
        emit_error 1 "Failed to parse workspace: ${LATEST_WS}"
    fi
fi

# No workspace found at all - not necessarily an error (e.g., explorer agents)
exit 0
