#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Test Environment Setup
# Usage: ./setup.sh anki v8
# Usage: ./setup.sh pipeline v8

TEMPLATE=$1
VERSION=$2

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./setup.sh <template> <version>"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./setup.sh anki v8"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="$EVAL_DIR/template_${TEMPLATE}"
TARGET="$EVAL_DIR/../../scratch/${TEMPLATE}-${VERSION}"

if [ ! -d "$TEMPLATE_DIR" ]; then
    echo "Error: Template not found: $TEMPLATE_DIR"
    echo "Available templates:"
    ls -1 "$EVAL_DIR" | grep "^template_" | sed 's/template_/  /'
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
