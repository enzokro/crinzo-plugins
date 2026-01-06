#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Plugin Propagation
# Force-syncs plugin source to Claude cache (claude plugin update doesn't re-copy)
# Usage: ./propagate.sh "commit message"

MSG=${1:-"eval: plugin update"}
EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
FTL_ROOT="$EVAL_DIR/.."
PLUGIN_JSON="$FTL_ROOT/.claude-plugin/plugin.json"
REPO_ROOT="$FTL_ROOT/.."
CACHE_ROOT="$HOME/.claude/plugins/cache/crinzo-plugins/ftl"

cd "$REPO_ROOT"

# Check for uncommitted changes in ftl/
if ! git diff --quiet ftl/; then
    echo "Uncommitted FTL changes detected"

    # Bump version (patch)
    CURRENT=$(jq -r .version "$PLUGIN_JSON")
    IFS='.' read -r MAJOR MINOR PATCH <<< "$CURRENT"
    NEW_VERSION="$MAJOR.$MINOR.$((PATCH + 1))"

    # Update plugin.json
    jq ".version = \"$NEW_VERSION\"" "$PLUGIN_JSON" > "$PLUGIN_JSON.tmp" && mv "$PLUGIN_JSON.tmp" "$PLUGIN_JSON"

    # Commit
    git add ftl/
    git commit -m "$MSG

Version: $NEW_VERSION"

    echo "Committed as v$NEW_VERSION"
else
    echo "No uncommitted FTL changes"
fi

# Get current version
VERSION=$(jq -r .version "$PLUGIN_JSON")
CACHE_DIR="$CACHE_ROOT/$VERSION"

echo "Force-syncing plugin to cache..."
echo "  Source: $FTL_ROOT"
echo "  Target: $CACHE_DIR"

# Flush existing cache for this version
if [ -d "$CACHE_DIR" ]; then
    echo "  Removing stale cache: $CACHE_DIR"
    rm -rf "$CACHE_DIR"
fi

# Copy fresh from source
mkdir -p "$CACHE_DIR"
cp -r "$FTL_ROOT"/* "$CACHE_DIR/"

# Verify critical file
if grep -q "CAMPAIGN mode.*DO NOT spawn learner" "$CACHE_DIR/skills/ftl/SKILL.md" 2>/dev/null; then
    echo "  ✓ Learner skip instruction present in cache"
else
    echo "  ⚠ WARNING: Learner skip instruction NOT found in cached SKILL.md"
fi

echo ""
echo "Plugin v$VERSION force-synced to cache"
echo "Restart Claude to load updated plugin"
