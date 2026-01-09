#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Reflection Runner
# Usage: ./scripts/reflect.sh anki v25
#
# Invokes meta-reflector agent to analyze run and update reflections

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
FTL_DIR="$(cd "$EVAL_DIR/.." && pwd)"

TEMPLATE=$1
VERSION=$2

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/reflect.sh <template> <version>"
    echo "Example: ./scripts/reflect.sh anki v25"
    exit 1
fi

RUN_ID="${TEMPLATE}-${VERSION}"
EVIDENCE_DIR="$EVAL_DIR/evidence/runs/$RUN_ID"
REFLECTIONS_DIR="$EVAL_DIR/reflections"

if [ ! -d "$EVIDENCE_DIR" ]; then
    echo "Error: Evidence not found at $EVIDENCE_DIR"
    echo "Run capture first: ./eval.sh capture $RUN_ID"
    exit 1
fi

# Find previous run for comparison (same template, lower version)
PREV_RUN=""
for dir in $(ls -1d "$EVAL_DIR/evidence/runs/${TEMPLATE}-v"* 2>/dev/null | sort -V); do
    dir_name=$(basename "$dir")
    if [ "$dir_name" != "$RUN_ID" ]; then
        # Check if this version is lower than current
        prev_ver=$(echo "$dir_name" | sed "s/${TEMPLATE}-v//")
        curr_ver=$(echo "$VERSION" | sed 's/v//')
        if [ "$prev_ver" -lt "$curr_ver" ] 2>/dev/null; then
            PREV_RUN="$dir"
        fi
    fi
done

# Build previous argument
PREV_ARG=""
PREV_DISPLAY="(none - first run)"
if [ -n "$PREV_RUN" ]; then
    PREV_ARG="--previous $PREV_RUN"
    PREV_DISPLAY="$PREV_RUN"
fi

echo "========================================================================"
echo "                    META-REFLECTION: $RUN_ID"
echo "========================================================================"
echo ""
echo "Evidence:    $EVIDENCE_DIR"
echo "Reflections: $REFLECTIONS_DIR"
echo "Previous:    $PREV_DISPLAY"
echo ""

# Read the meta-reflector agent protocol
AGENT_PROTOCOL="$FTL_DIR/agents/meta-reflector.md"
if [ ! -f "$AGENT_PROTOCOL" ]; then
    echo "Error: meta-reflector.md not found at $AGENT_PROTOCOL"
    exit 1
fi

# Build the prompt with absolute paths
PROMPT="You are the meta-reflector agent. Analyze this completed run and update reflections.

## Paths (all absolute)

--evidence $EVIDENCE_DIR
--reflections $REFLECTIONS_DIR
$PREV_ARG

## Protocol

$(cat "$AGENT_PROTOCOL" | tail -n +8)

## Your Task

1. Read the evidence files at the paths above
2. Read the current reflection files
3. Analyze the run, compare to previous if available
4. Update the reflection files (journal.md always, others as needed)
5. Output a summary of what you updated

Begin by reading $EVIDENCE_DIR/metrics.json"

# Invoke Claude headlessly
# Using bypassPermissions since this is an automated evaluation context
claude -p "$PROMPT" \
    --output-format text \
    --permission-mode bypassPermissions \
    --allowedTools "Read,Edit,Glob,Grep" \
    --max-budget-usd 5

echo ""
echo "========================================================================"
echo "Reflection complete. Check $REFLECTIONS_DIR for updates."
echo "========================================================================"
