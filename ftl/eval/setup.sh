#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Test Environment Setup
# Usage: ./setup.sh v8

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: ./setup.sh <version>"
    echo "Example: ./setup.sh v8"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
TARGET="$EVAL_DIR/../../scratch/mock-anki-app-$VERSION"

if [ -d "$TARGET" ]; then
    echo "Error: $TARGET already exists"
    exit 1
fi

# Copy template
cp -r "$EVAL_DIR/template" "$TARGET"

# Initialize uv environment
cd "$TARGET"
uv sync

echo "Created: $TARGET"
echo "Ready for campaign"
