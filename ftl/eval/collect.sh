#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Agent Log Collection
# Usage: ./collect.sh v8

VERSION=$1

if [ -z "$VERSION" ]; then
    echo "Usage: ./collect.sh <version>"
    echo "Example: ./collect.sh v8"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_PROJECTS="$HOME/.claude/projects"

# Derive Claude project directory name from path
# /path/to/scratch/mock-anki-app-v8 -> -path-to-scratch-mock-anki-app-v8
TARGET="$EVAL_DIR/../../scratch/mock-anki-app-$VERSION"
if [ ! -d "$TARGET" ]; then
    echo "Error: $TARGET does not exist"
    exit 1
fi

FULL_PATH=$(cd "$TARGET" && pwd)
PROJECT_NAME=$(echo "$FULL_PATH" | sed 's|/|-|g')

RESULTS_DIR="$EVAL_DIR/results/$VERSION"
mkdir -p "$RESULTS_DIR"

# Copy agent logs
SOURCE_DIR="$CLAUDE_PROJECTS/$PROJECT_NAME"
if ls "$SOURCE_DIR"/agent-*.jsonl 1>/dev/null 2>&1; then
    cp "$SOURCE_DIR"/agent-*.jsonl "$RESULTS_DIR/"
    echo "Copied agent logs to $RESULTS_DIR/"
else
    echo "No agent logs found at $SOURCE_DIR/"
    echo "Available projects:"
    ls "$CLAUDE_PROJECTS" | grep mock-anki || echo "(none)"
    exit 1
fi

# Run analysis
python3 "$EVAL_DIR/analyze.py" "$RESULTS_DIR" > "$RESULTS_DIR/summary.txt"
python3 "$EVAL_DIR/analyze.py" "$RESULTS_DIR" --json > "$RESULTS_DIR/summary.json"

echo "Analysis complete: $RESULTS_DIR/summary.txt"
cat "$RESULTS_DIR/summary.txt"
