#!/bin/bash
## NOTE:: FUTURE FIX
# This script is called by campaign.sh as a shell pre-hook.
# It creates .ftl/cache/session_context.md with:
# - Git state (branch, recent commits)
# - Project verification tools
# - Prior knowledge from .ftl/memory.json (v3.0 format)
#
# This is a workaround because:
# - SKILL.md bash code blocks are not executed by Claude
# - Agents need context BEFORE they start reasoning
#
# Future: Replace with formal FTL hook system that:
# - Discovers hooks from hooks/ directory
# - Runs pre-campaign hooks before skill invocation
# - Supports hook dependencies and ordering
## END NOTE
#
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

# Inject prior knowledge from memory.json v3.0 (cross-run learning)
MEMORY_FILE=".ftl/memory.json"
if [ -f "$MEMORY_FILE" ]; then
  # Check if memory has any discoveries or failures (v3.0 uses discoveries, v2.0 used patterns)
  DISCOVERY_COUNT=$(jq '.discoveries | length' "$MEMORY_FILE" 2>/dev/null || jq '.patterns | length' "$MEMORY_FILE" 2>/dev/null || echo "0")
  FAILURE_COUNT=$(jq '.failures | length' "$MEMORY_FILE" 2>/dev/null || echo "0")

  if [ "$DISCOVERY_COUNT" -gt 0 ] || [ "$FAILURE_COUNT" -gt 0 ]; then
    echo "" >> .ftl/cache/session_context.md
    echo "## Prior Knowledge (from previous campaigns)" >> .ftl/cache/session_context.md
    echo "" >> .ftl/cache/session_context.md

    # Load FTL lib path and use memory.py to format injection
    source ~/.config/ftl/paths.sh 2>/dev/null

    if [ -n "$FTL_LIB" ] && [ -f "$FTL_LIB/memory.py" ]; then
      # Use memory.py for proper formatting AND tracking
      # Generate run_id from timestamp and random suffix
      RUN_ID="run-$(date +%Y%m%d-%H%M%S)-$$"

      python3 -c "
import sys
sys.path.insert(0, '$FTL_LIB')
from memory import load_memory, inject_and_log
from pathlib import Path

memory = load_memory(Path('$MEMORY_FILE'))
log_path = Path('.ftl/results/injection.json')
log_path.parent.mkdir(parents=True, exist_ok=True)

# Use inject_and_log for proper tracking
markdown, injection_log = inject_and_log(
    memory,
    run_id='$RUN_ID',
    log_path=log_path
)
print(markdown)
" >> .ftl/cache/session_context.md
    else
      # Fallback: inline formatting if memory.py not available (v3.0 schema)
      echo "### Known Failures" >> .ftl/cache/session_context.md
      echo "" >> .ftl/cache/session_context.md
      jq -r '.failures[] | "- **\(.name)** (cost: \(.cost // 0)k)\n  Trigger: \(.trigger)\n  Fix: \(.fix)\n"' "$MEMORY_FILE" 2>/dev/null >> .ftl/cache/session_context.md

      # Pre-flight checks from failures with prevent field
      PREFLIGHT=$(jq -r '.failures[] | select(.prevent) | "- [ ] `\(.prevent)`"' "$MEMORY_FILE" 2>/dev/null)
      if [ -n "$PREFLIGHT" ]; then
        echo "### Pre-flight Checks" >> .ftl/cache/session_context.md
        echo "" >> .ftl/cache/session_context.md
        echo "Before verify, run:" >> .ftl/cache/session_context.md
        echo "$PREFLIGHT" >> .ftl/cache/session_context.md
        echo "" >> .ftl/cache/session_context.md
      fi

      echo "### Discoveries" >> .ftl/cache/session_context.md
      echo "" >> .ftl/cache/session_context.md
      jq -r '.discoveries[] | "- **\(.name)** (saved: \(.tokens_saved // 0)k)\n  When: \(.trigger)\n  Insight: \(.insight)\n"' "$MEMORY_FILE" 2>/dev/null >> .ftl/cache/session_context.md
    fi

    echo "" >> .ftl/cache/session_context.md
    echo "**Memory seeded**: $DISCOVERY_COUNT discoveries, $FAILURE_COUNT failures available." >> .ftl/cache/session_context.md
    echo "Prior knowledge injected from $MEMORY_FILE ($DISCOVERY_COUNT discoveries, $FAILURE_COUNT failures)"
  else
    echo "Memory file exists but empty (de novo run)"
  fi
else
  echo "No memory file found (de novo run)"
fi

echo "Session context cached to .ftl/cache/session_context.md"
exit 0
