#!/bin/bash
# session_context.sh - Pre-cache STATIC project metadata at session start
# Writes to .ftl/cache/session_context.md for orchestrator to read and inject
#
# Caches STATIC info only (doesn't change during session):
#   - Git state (branch, recent commits)
#   - Project verification tools (package.json scripts, Makefile targets)
#
# DYNAMIC cognition state is cached separately by orchestrator
# after each agent completes → .ftl/cache/cognition_state.md
#
# The orchestrator (SKILL.md) reads BOTH files and injects into router prompts.

# Ensure cache directory exists
mkdir -p .ftl/cache 2>/dev/null

# Git state (stable within session)
GIT_BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
GIT_RECENT=$(git log --oneline -3 2>/dev/null | tr '\n' '; ' || echo "no history")

# Project verification tools (stable within session)
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

# Write STATIC context to file
cat > .ftl/cache/session_context.md << EOF
## FTL Session Context (Static - Cached at Session Start)

Cached at: $(date -u +%Y-%m-%dT%H:%M:%SZ)

### Git State
- Branch: $GIT_BRANCH
- Recent commits: $GIT_RECENT

### Project Verification Tools
- Package.json scripts: $PKG_SCRIPTS
- Makefile targets: $MAKEFILE_TARGETS
- Pyproject test config: $PYPROJECT_TEST

**DO NOT re-run**: \`git branch\`, \`cat package.json\`, \`cat Makefile\` — this info is current.

**For cognition state**: See \`.ftl/cache/cognition_state.md\` (updated after each agent).
EOF

echo "Session context cached to .ftl/cache/session_context.md"
exit 0
