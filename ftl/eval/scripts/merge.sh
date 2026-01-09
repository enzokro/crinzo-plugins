#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Pattern Merge
# Usage: ./scripts/merge.sh anki v25 /path/to/synthesis.json
#
# Merges synthesis.json from a completed run into the persistent accumulator.
# GIGO protection is handled by the Python script.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

TEMPLATE=$1
VERSION=$2
SYNTHESIS_PATH=$3

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ] || [ -z "$SYNTHESIS_PATH" ]; then
    echo "Usage: ./scripts/merge.sh <template> <version> <synthesis-path>"
    echo ""
    echo "Merges run synthesis into accumulator at eval/memory/patterns/<template>.json"
    exit 1
fi

if [ ! -f "$SYNTHESIS_PATH" ]; then
    echo "Warning: Synthesis file not found at $SYNTHESIS_PATH"
    echo "Skipping merge (run may not have completed synthesis phase)"
    exit 0
fi

# Ensure memory directory exists
mkdir -p "$EVAL_DIR/memory/patterns"

# Run merge with GIGO protection
python3 "$EVAL_DIR/instruments/merge_patterns.py" \
    --template "$TEMPLATE" \
    --version "$VERSION" \
    --synthesis "$SYNTHESIS_PATH" \
    --accumulator "$EVAL_DIR/memory/patterns/${TEMPLATE}.json"
