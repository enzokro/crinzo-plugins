#!/bin/bash
# Run meta_eval.sh for all (or selected) templates
# Usage: ./meta_eval_suite.sh v43 [templates] [--force]
# Examples:
#   ./meta_eval_suite.sh v43                    # All templates
#   ./meta_eval_suite.sh v43 anki,errors        # Only anki and errors
#   ./meta_eval_suite.sh v43 anki --force       # Single template, force

set -e

VERSION="${1:?Usage: $0 <version> [templates] [--force]}"
shift

# Parse remaining args
FORCE=""
TEMPLATES="anki errors pipeline refactor"

for arg in "$@"; do
    if [[ "$arg" == "--force" ]]; then
        FORCE="--force"
    elif [[ "$arg" == *","* ]] || [[ "anki errors pipeline refactor" == *"$arg"* ]]; then
        TEMPLATES="${arg//,/ }"
    fi
done

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "════════════════════════════════════════════════════════════════"
echo "  META-EVAL SUITE: $VERSION"
echo "════════════════════════════════════════════════════════════════"
echo ""

for T in $TEMPLATES; do
    echo ""
    echo "┌──────────────────────────────────────────────────────────────┐"
    echo "│  TEMPLATE: $T"
    echo "└──────────────────────────────────────────────────────────────┘"
    "$EVAL_DIR/meta_eval.sh" "$T" "$VERSION" $FORCE || {
        echo "⚠️  $T failed - continuing with next template"
    }
done

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  SUITE COMPLETE: $VERSION"
echo "════════════════════════════════════════════════════════════════"
