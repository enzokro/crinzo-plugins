#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Campaign Runner
# Usage: ./campaign.sh v8 ["custom objective"]

VERSION=$1
OBJECTIVE=${2:-"build a flashcard study app with spaced repetition"}

if [ -z "$VERSION" ]; then
    echo "Usage: ./campaign.sh <version> [objective]"
    echo "Example: ./campaign.sh v8 'build a todo app'"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$EVAL_DIR/../../scratch/mock-anki-app-$VERSION"

if [ ! -d "$TARGET" ]; then
    echo "Error: $TARGET does not exist"
    echo "Run setup.sh first: ./setup.sh $VERSION"
    exit 1
fi

cd "$TARGET"

echo "Starting campaign in $TARGET"
echo "Objective: $OBJECTIVE"
echo ""

# Run Claude in print mode with skill invocation
claude -p "/ftl:ftl campaign \"$OBJECTIVE\"" \
    --output-format text \
    --permission-mode dontAsk \
    --max-budget-usd 50

echo ""
echo "Campaign complete"
