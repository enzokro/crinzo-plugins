#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Test Environment Setup
# Usage: ./scripts/setup.sh anki v8

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TEMPLATE=$1
VERSION=$2

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/setup.sh <template> <version>"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./scripts/setup.sh anki v8"
    exit 1
fi

TEMPLATE_DIR="$EVAL_DIR/templates/${TEMPLATE}"
TARGET="$EVAL_DIR/../../scratch/${TEMPLATE}-${VERSION}"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "Error: Template not found: $TEMPLATE_DIR"
    echo "Available templates:"
    ls -1 "$EVAL_DIR/templates"
    exit 1
fi

if [ -d "$TARGET" ]; then
    echo "Error: $TARGET already exists"
    exit 1
fi

# Copy template
cp -r "$TEMPLATE_DIR" "$TARGET"

# Initialize uv environment
cd "$TARGET"
uv sync

echo "Created: $TARGET"
echo "Ready for campaign"
