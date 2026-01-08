#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Campaign Runner
# Usage: ./scripts/campaign.sh anki v8

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TEMPLATE=$1
VERSION=$2
CUSTOM_OBJECTIVE=$3

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/campaign.sh <template> <version> [objective]"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./scripts/campaign.sh anki v8"
    exit 1
fi

# Template-specific default objectives
case "$TEMPLATE" in
    anki)
        DEFAULT_OBJECTIVE="build the flashcard app per README.md - see REQUIRED TASK BREAKDOWN for exact tasks"
        ;;
    pipeline)
        DEFAULT_OBJECTIVE="build a CSV data pipeline with validation, transformation, and aggregation"
        ;;
    errors)
        DEFAULT_OBJECTIVE="build a config parser with strict validation and helpful error messages"
        ;;
    refactor)
        DEFAULT_OBJECTIVE="extend and refactor the existing task manager to add priorities, due dates, and filtering"
        ;;
    *)
        echo "Unknown template: $TEMPLATE"
        echo "Available: anki, pipeline, errors, refactor"
        exit 1
        ;;
esac

OBJECTIVE=${CUSTOM_OBJECTIVE:-$DEFAULT_OBJECTIVE}

TARGET="$EVAL_DIR/../../scratch/${TEMPLATE}-${VERSION}"

if [ ! -d "$TARGET" ]; then
    echo "Error: $TARGET does not exist"
    echo "Run setup.sh first: ./scripts/setup.sh $TEMPLATE $VERSION"
    exit 1
fi

cd "$TARGET"

echo "Starting campaign in $TARGET"
echo "Template: $TEMPLATE"
echo "Objective: $OBJECTIVE"
echo ""

# Run Claude in print mode with skill invocation
claude -p "/ftl:ftl campaign \"$OBJECTIVE\"" \
    --output-format text \
    --permission-mode bypassPermissions \
    --allowedTools "Bash,Read,Write,Edit,Glob,Grep,Task" \
    --max-budget-usd 50

echo ""
echo "Campaign complete"
