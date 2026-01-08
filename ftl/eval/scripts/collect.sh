#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Agent Log Collection
# Usage: ./scripts/collect.sh anki v8

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TEMPLATE=$1
VERSION=$2

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/collect.sh <template> <version>"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./scripts/collect.sh anki v8"
    exit 1
fi

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

# Copy all session logs (agents + main orchestrator)
SOURCE_DIR="$CLAUDE_PROJECTS/$PROJECT_NAME"
if ls "$SOURCE_DIR"/*.jsonl 1>/dev/null 2>&1; then
    cp "$SOURCE_DIR"/*.jsonl "$RESULTS_DIR/"

    # Report what was collected
    AGENT_COUNT=$(ls "$RESULTS_DIR"/agent-*.jsonl 2>/dev/null | wc -l | tr -d ' ')
    MAIN_COUNT=$(ls "$RESULTS_DIR"/*.jsonl 2>/dev/null | grep -v "agent-" | wc -l | tr -d ' ')
    echo "Copied $AGENT_COUNT agent logs + $MAIN_COUNT main session(s) to $RESULTS_DIR/"
else
    echo "No JSONL logs found at $SOURCE_DIR/"
    echo "Available projects:"
    ls "$CLAUDE_PROJECTS" | grep "${TEMPLATE}" || echo "(none matching ${TEMPLATE})"
    exit 1
fi

echo "Collection complete: $RESULTS_DIR"
echo "Run './eval.sh capture ${TEMPLATE}-${VERSION}' to extract evidence"
