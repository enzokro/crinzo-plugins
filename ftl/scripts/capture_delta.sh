#!/bin/bash
# capture_delta.sh - Runs after router completes via SubagentStop
# Extracts Delta files from workspace, caches contents for Builder injection

set -e

# Clear stale cache
rm -rf .ftl/cache/* 2>/dev/null || true

# Consume stdin (hook input)
INPUT=$(cat)

# Find active workspace file
WORKSPACE=$(find .ftl/workspace -name "*_active.md" 2>/dev/null | head -1)
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
