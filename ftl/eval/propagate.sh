#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Plugin Propagation
# Usage: ./propagate.sh "commit message"

MSG=${1:-"eval: plugin update"}
EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
FTL_ROOT="$EVAL_DIR/.."
PLUGIN_JSON="$FTL_ROOT/.claude-plugin/plugin.json"
REPO_ROOT="$FTL_ROOT/.."

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

# Update Claude plugin cache
echo "Updating Claude plugin cache..."
claude plugin update ftl@crinzo-plugins

echo "Plugin propagated"
