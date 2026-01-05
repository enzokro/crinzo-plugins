#!/bin/bash
# session_context.sh - Pre-cache project metadata at session start
# Injects via additionalContext so all agents receive this without re-querying
#
# Caches:
#   - Git state (branch, recent commits)
#   - Project verification tools (package.json scripts, Makefile targets)
#   - Workspace state (active tasks, recent completed)
#   - Active campaign info

# Ensure cache directory exists
mkdir -p .ftl/cache 2>/dev/null

# Git state
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
GIT_RECENT=$(git log --oneline -3 2>/dev/null | tr '\n' '; ' || echo "no history")

# Project verification tools
PKG_SCRIPTS=""
if [ -f "package.json" ]; then
  PKG_SCRIPTS=$(cat package.json 2>/dev/null | jq -c '.scripts // {}' 2>/dev/null || echo "{}")
fi

MAKEFILE_TARGETS=""
if [ -f "Makefile" ]; then
  MAKEFILE_TARGETS=$(grep -E '^[a-z][a-z0-9_-]*:' Makefile 2>/dev/null | cut -d: -f1 | tr '\n' ' ' || echo "")
fi

PYPROJECT_TEST=""
if [ -f "pyproject.toml" ]; then
  PYPROJECT_TEST=$(grep -A5 '\[tool.pytest' pyproject.toml 2>/dev/null | head -5 || echo "")
fi

# Workspace state
ACTIVE_TASKS=$(ls .ftl/workspace/*_active*.md 2>/dev/null | wc -l | tr -d ' ')
RECENT_COMPLETE=$(ls -t .ftl/workspace/*_complete*.md 2>/dev/null | head -3 | tr '\n' ' ')

# Active campaign
CAMPAIGN=""
if [ -f ".ftl/campaign.json" ]; then
  CAMPAIGN=$(cat .ftl/campaign.json 2>/dev/null | jq -c '{objective, status, tasks_complete: (.tasks | map(select(.status == "complete")) | length), tasks_total: (.tasks | length)}' 2>/dev/null || echo "{}")
fi

# Build context string (escape for JSON)
CONTEXT="## FTL Session Context (Pre-Cached)

### Git State
- Branch: $GIT_BRANCH
- Recent commits: $GIT_RECENT

### Project Verification Tools
- Package.json scripts: $PKG_SCRIPTS
- Makefile targets: $MAKEFILE_TARGETS
- Pyproject test config: $PYPROJECT_TEST

### Workspace State
- Active tasks: $ACTIVE_TASKS
- Recent completed: $RECENT_COMPLETE

### Campaign
$CAMPAIGN

**Use this pre-cached information instead of re-running discovery commands.**"

# Escape for JSON (handle newlines and quotes)
ESCAPED_CONTEXT=$(echo "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo "\"$CONTEXT\"")

# Output as additionalContext JSON
cat << EOF
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": $ESCAPED_CONTEXT
  }
}
EOF

exit 0
