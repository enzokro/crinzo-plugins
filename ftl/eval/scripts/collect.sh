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
FOUND_FILES=0

# Copy main session logs from project root
if ls "$SOURCE_DIR"/*.jsonl 1>/dev/null 2>&1; then
    cp "$SOURCE_DIR"/*.jsonl "$RESULTS_DIR/"
    FOUND_FILES=1
fi

# NEW: Copy agent logs from session subagents directories
# Claude Code now stores subagent files in: <session-id>/subagents/agent-*.jsonl
for SESSION_DIR in "$SOURCE_DIR"/*/; do
    if [ -d "$SESSION_DIR/subagents" ]; then
        if ls "$SESSION_DIR/subagents"/agent-*.jsonl 1>/dev/null 2>&1; then
            cp "$SESSION_DIR/subagents"/agent-*.jsonl "$RESULTS_DIR/"
            FOUND_FILES=1
        fi
    fi
done

# Also check for legacy agent-*.jsonl in project root (older Claude Code versions)
if ls "$SOURCE_DIR"/agent-*.jsonl 1>/dev/null 2>&1; then
    # Don't overwrite if already copied from subagents
    for f in "$SOURCE_DIR"/agent-*.jsonl; do
        BASENAME=$(basename "$f")
        if [ ! -f "$RESULTS_DIR/$BASENAME" ]; then
            cp "$f" "$RESULTS_DIR/"
        fi
    done
    FOUND_FILES=1
fi

if [ "$FOUND_FILES" -eq 0 ]; then
    echo "No JSONL logs found at $SOURCE_DIR/"
    echo "Available projects:"
    ls "$CLAUDE_PROJECTS" | grep "${TEMPLATE}" || echo "(none matching ${TEMPLATE})"
    exit 1
fi

# Report what was collected
AGENT_COUNT=$(ls "$RESULTS_DIR"/agent-*.jsonl 2>/dev/null | wc -l | tr -d ' ')
MAIN_COUNT=$(ls "$RESULTS_DIR"/*.jsonl 2>/dev/null | grep -v "agent-" | wc -l | tr -d ' ')
echo "Copied $AGENT_COUNT agent logs + $MAIN_COUNT main session(s) to $RESULTS_DIR/"

echo "Collection complete: $RESULTS_DIR"
echo "Run './eval.sh capture ${TEMPLATE}-${VERSION}' to extract evidence"
