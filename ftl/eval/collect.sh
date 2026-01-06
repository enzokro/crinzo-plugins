#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Agent Log Collection
# Usage: ./collect.sh anki v8

TEMPLATE=$1
VERSION=$2

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./collect.sh <template> <version>"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./collect.sh anki v8"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_PROJECTS="$HOME/.claude/projects"

# Derive Claude project directory name from path
TARGET="$EVAL_DIR/../../scratch/${TEMPLATE}-${VERSION}"
if [ ! -d "$TARGET" ]; then
    echo "Error: $TARGET does not exist"
    exit 1
fi

FULL_PATH=$(cd "$TARGET" && pwd)
PROJECT_NAME=$(echo "$FULL_PATH" | sed 's|/|-|g')

RESULTS_DIR="$EVAL_DIR/results/${TEMPLATE}-${VERSION}"
mkdir -p "$RESULTS_DIR"

# Copy agent logs
SOURCE_DIR="$CLAUDE_PROJECTS/$PROJECT_NAME"
if ls "$SOURCE_DIR"/agent-*.jsonl 1>/dev/null 2>&1; then
    cp "$SOURCE_DIR"/agent-*.jsonl "$RESULTS_DIR/"
    echo "Copied agent logs to $RESULTS_DIR/"
else
    echo "No agent logs found at $SOURCE_DIR/"
    echo "Available projects:"
    ls "$CLAUDE_PROJECTS" | grep "${TEMPLATE}" || echo "(none matching ${TEMPLATE})"
    exit 1
fi

# Run analysis
python3 "$EVAL_DIR/analyze.py" "$RESULTS_DIR" > "$RESULTS_DIR/summary.txt"
python3 "$EVAL_DIR/analyze.py" "$RESULTS_DIR" --json > "$RESULTS_DIR/summary.json"

echo "Analysis complete: $RESULTS_DIR/summary.txt"
cat "$RESULTS_DIR/summary.txt"
