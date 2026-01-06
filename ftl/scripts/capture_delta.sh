#!/bin/bash
# capture_delta.sh - Cache Delta files AND workspace state after each agent
# Called by SubagentStop hook. Uses CLAUDE_PROJECT_DIR if available.
#
# Caches TWO things:
#   1. delta_contents.md - Delta file contents for builder/learner
#   2. workspace_state.md - Current workspace state (evolves per task)
#
# Flow:
#   Router completes → captures pre-edit Delta + workspace state
#   Builder completes → captures post-edit Delta + workspace state
#   Learner completes → updates workspace state only

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CACHE_DIR="$PROJECT_DIR/.ftl/cache"
WORKSPACE_DIR="$PROJECT_DIR/.ftl/workspace"

mkdir -p "$CACHE_DIR"

# Consume stdin (hook input)
cat > /dev/null

# ============================================================
# Part 1: Update workspace_state.md (ALWAYS runs)
# ============================================================
LAST_SEQ=$(ls "$WORKSPACE_DIR/" 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1)
[ -z "$LAST_SEQ" ] && LAST_SEQ="000"

ACTIVE_TASKS=$(ls "$WORKSPACE_DIR/"*_active*.md 2>/dev/null | wc -l | tr -d ' ')
RECENT_COMPLETE=$(ls -t "$WORKSPACE_DIR/"*_complete*.md 2>/dev/null | head -5 | xargs -I{} basename {} 2>/dev/null | tr '\n' ', ' | sed 's/,$//')

# Active campaign info
CAMPAIGN=""
if [ -f "$PROJECT_DIR/.ftl/campaign.json" ]; then
  CAMPAIGN=$(cat "$PROJECT_DIR/.ftl/campaign.json" 2>/dev/null | jq -c '{objective, status, tasks_complete: (.tasks | map(select(.status == "complete")) | length), tasks_total: (.tasks | length)}' 2>/dev/null || echo "{}")
fi

cat > "$CACHE_DIR/workspace_state.md" << EOF
## FTL Workspace State (Dynamic - Updated After Each Agent)

Updated at: $(date -u +%Y-%m-%dT%H:%M:%SZ)

### Workspace
- Last sequence number: $LAST_SEQ
- Active tasks: $ACTIVE_TASKS
- Recent completed: $RECENT_COMPLETE

### Campaign
$CAMPAIGN

**DO NOT re-run**: \`ls .ftl/workspace/\` — this info is current.
EOF

# ============================================================
# Part 2: Cache Delta contents (only if workspace exists)
# ============================================================

# Clear stale Delta cache
rm -f "$CACHE_DIR/delta_contents.md" 2>/dev/null || true

# Find workspace (prefer active, fall back to most recent complete)
WORKSPACE=$(find "$WORKSPACE_DIR" -name "*_active*.md" 2>/dev/null | head -1)
[ -z "$WORKSPACE" ] && WORKSPACE=$(ls -t "$WORKSPACE_DIR/"*_complete*.md 2>/dev/null | head -1)
[ -z "$WORKSPACE" ] && exit 0

# Extract Delta field (under ## Implementation section)
DELTA_LINE=$(grep "^Delta:" "$WORKSPACE" 2>/dev/null | head -1)
[ -z "$DELTA_LINE" ] && exit 0

# Parse comma-separated paths
DELTA_FILES=$(echo "$DELTA_LINE" | sed 's/Delta: //' | tr ',' '\n' | sed 's/^ *//' | sed 's/ *$//')
[ -z "$DELTA_FILES" ] && exit 0

{
  echo "# Delta File Contents (Cached)"
  echo ""
  echo "Cached at: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "Source workspace: $WORKSPACE"
  echo ""
  echo "**Use these contents instead of re-reading the files.**"
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
