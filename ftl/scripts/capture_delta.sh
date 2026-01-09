#!/bin/bash
# capture_delta.sh - Cache Cognition State + Delta files after each agent
# Called by SubagentStop hook. Uses CLAUDE_PROJECT_DIR if available.
#
# Caches TWO things:
#   1. cognition_state.md - Phase model, inherited knowledge, operational state
#   2. delta_contents.md - Delta file contents for builder/learner
#
# The cognition cache is not just state — it's how agents inherit knowledge.
# Without it, downstream agents re-learn what upstream agents already knew.

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CACHE_DIR="$PROJECT_DIR/.ftl/cache"
WORKSPACE_DIR="$PROJECT_DIR/.ftl/workspace"

mkdir -p "$CACHE_DIR"

# Consume stdin (hook input)
cat > /dev/null

# ============================================================
# Part 1: Update cognition_state.md (ALWAYS runs)
# ============================================================
LAST_SEQ=$(ls "$WORKSPACE_DIR/" 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1)
[ -z "$LAST_SEQ" ] && LAST_SEQ="000"

ACTIVE=$(ls "$WORKSPACE_DIR/"*_active*.md 2>/dev/null | xargs -I{} basename {} 2>/dev/null | tr '\n' ', ' | sed 's/,$//' || echo "none")
[ -z "$ACTIVE" ] && ACTIVE="none"

RECENT=$(ls -t "$WORKSPACE_DIR/"*_complete*.md 2>/dev/null | head -3 | xargs -I{} basename {} 2>/dev/null | tr '\n' ', ' | sed 's/,$//' || echo "none")
[ -z "$RECENT" ] && RECENT="none"

# Campaign context
CAMPAIGN_OBJ=""
if [ -f "$PROJECT_DIR/.ftl/campaign.json" ]; then
  CAMPAIGN_OBJ=$(cat "$PROJECT_DIR/.ftl/campaign.json" 2>/dev/null | jq -r '.objective // empty' 2>/dev/null || echo "")
fi

cat > "$CACHE_DIR/cognition_state.md" << EOF
# Cognition State
*Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)*

## Phase Model

You inherit knowledge from prior phases. You do not re-learn it.

| Phase | Agent | Output |
|-------|-------|--------|
| LEARNING | planner | task breakdown, verification commands |
| SCOPING | router | Delta, Path, precedent |
| EXECUTION | builder | code within Delta |
| EXTRACTION | learner/synthesizer | patterns |

**Category test**: Am I thinking "let me understand X first"?
→ That thought is incoherent. Understanding happened in prior phases.
→ If knowledge feels insufficient, return: "Workspace incomplete: need [X]"

## Inherited Knowledge

Planner analyzed: objective, requirements, verification approach
Router scoped: Delta bounds, data transformation Path, related precedent

**This knowledge is in your workspace file. Read it. Trust it. Execute from it.**

## Operational State

Last sequence: $LAST_SEQ
Active: $ACTIVE
Recent: $RECENT
${CAMPAIGN_OBJ:+Campaign: $CAMPAIGN_OBJ}

## If You're About to Explore

STOP. Ask yourself:
1. Is this file in my Delta? If no → out of scope, do not read
2. Did planner/router already analyze this? If yes → knowledge is in workspace
3. Am I learning or executing? If learning → wrong phase

Exploration during execution costs ~10x more than exploration during routing.
The correct response to insufficient knowledge is escalation, not exploration.
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
