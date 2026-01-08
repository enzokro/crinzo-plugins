#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Plugin Propagation
# Force-syncs plugin source to Claude cache
# Usage: ./scripts/propagate.sh "commit message"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

MSG=${1:-"eval: plugin update"}
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

# Clear out the entire old cache
if [ -d "$CACHE_ROOT" ]; then
    echo "  Clearing entire old cache: $CACHE_ROOT"
    rm -rf "$CACHE_ROOT/*"
fi

# Copy fresh from source
mkdir -p "$CACHE_DIR"
cp -r "$FTL_ROOT"/* "$CACHE_DIR/"

# Verify critical ontology section
if grep -q "Two Workflows: Task vs Campaign" "$CACHE_DIR/skills/ftl/SKILL.md" 2>/dev/null; then
    echo "  ✓ Ontology section present in cache"
    if grep -q "Learner.*NEVER" "$CACHE_DIR/skills/ftl/SKILL.md" 2>/dev/null; then
        echo "  ✓ Agent matrix with Learner prohibition present"
    else
        echo "  ⚠ WARNING: Agent matrix not found in SKILL.md"
    fi
else
    echo "  ⚠ WARNING: Ontology section NOT found in cached SKILL.md"
fi

# Verify command duplicate removed
if [ -f "$CACHE_DIR/commands/ftl.md" ]; then
    echo "  ⚠ WARNING: commands/ftl.md still exists (should be deleted)"
else
    echo "  ✓ commands/ftl.md correctly removed (skill is single source)"
fi

echo ""
echo "Plugin v$VERSION force-synced to cache"
echo "Restart Claude to load updated plugin"
