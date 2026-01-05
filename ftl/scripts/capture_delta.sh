#!/bin/bash
# capture_delta.sh - Runs after Router or Builder completes via SubagentStop
# Extracts Delta files from workspace, caches contents for next agent injection
#
# Flow:
#   Router completes → captures pre-edit Delta files → Builder receives them
#   Builder completes → captures post-edit Delta files → Learner receives them

set -e

# Clear stale cache (each transition gets fresh state)
rm -rf .ftl/cache/* 2>/dev/null || true

# Consume stdin (hook input)
INPUT=$(cat)

# Find workspace file (prefer active, fall back to most recent complete)
WORKSPACE=$(find .ftl/workspace -name "*_active.md" 2>/dev/null | head -1)
[ -z "$WORKSPACE" ] && WORKSPACE=$(find .ftl/workspace -name "*_complete.md" 2>/dev/null | sort -r | head -1)
[ -z "$WORKSPACE" ] && exit 0

# Extract Delta paths from workspace (lines after "## Delta" until next ##)
DELTA_FILES=$(awk '/^## Delta/,/^## /{if(/^- /) print substr($0,3)}' "$WORKSPACE")
[ -z "$DELTA_FILES" ] && exit 0

# Cache each Delta file
CACHE_DIR=".ftl/cache"
mkdir -p "$CACHE_DIR"

{
  echo "# Delta File Contents (Cached)"
  echo ""
  echo "Cached at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Source workspace: $WORKSPACE"
  echo ""

  for file in $DELTA_FILES; do
    [ -f "$file" ] || continue
    echo "## $file"
    echo '```'
    cat "$file"
    echo '```'
    echo ""
  done
} > "$CACHE_DIR/delta_contents.md"

exit 0
