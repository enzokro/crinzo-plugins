#!/usr/bin/env bash
# FTL Router Exploration Capture
# Extracts Thinking Traces from workspace file for builder injection

# Find most recent active workspace
WORKSPACE=$(ls -t .ftl/workspace/*_active*.md 2>/dev/null | head -1)

if [ -z "$WORKSPACE" ]; then
    exit 0  # No active workspace; nothing to capture
fi

mkdir -p .ftl/cache

# Extract Implementation and Thinking Traces sections
# These contain the router's exploration findings
{
    echo "# Exploration Context"
    echo "*From: $(basename "$WORKSPACE")*"
    echo ""

    # Extract Implementation section (Path, Delta, Verify)
    sed -n '/^## Implementation$/,/^## /p' "$WORKSPACE" | head -n -1

    echo ""

    # Extract Thinking Traces section
    sed -n '/^## Thinking Traces$/,/^## /p' "$WORKSPACE" | head -n -1

} > .ftl/cache/exploration_context.md

exit 0
