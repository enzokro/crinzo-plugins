#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Full Eval Loop for Single Template
# Usage: ./run.sh anki v8 "optional commit message"
# Usage: ./run.sh pipeline v8

TEMPLATE=$1
VERSION=$2
MSG=${3:-"eval: $TEMPLATE-$VERSION"}

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./run.sh <template> <version> [commit message]"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./run.sh anki v8 'fix: enforce learner skip'"
    echo ""
    echo "For full suite: ./run_suite.sh v8"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EVAL_DIR"

RESULTS_DIR="$EVAL_DIR/results/${TEMPLATE}-${VERSION}"
mkdir -p "$RESULTS_DIR"
LOG_FILE="$RESULTS_DIR/eval.log"

# Logging function
log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Timer
START_TIME=$(date +%s)

echo "" > "$LOG_FILE"
log "========================================"
log "FTL EVALUATION: $TEMPLATE-$VERSION"
log "========================================"
log "Started: $(date)"
log "Template: $TEMPLATE"
log "Version: $VERSION"
log "Commit message: $MSG"
log ""

# Step 1: Propagate plugin changes
log "[1/5] PROPAGATE PLUGIN"
log "----------------------------------------"
./propagate.sh "$MSG" 2>&1 | tee -a "$LOG_FILE"
log ""

# Capture plugin version
PLUGIN_VERSION=$(jq -r .version "$EVAL_DIR/../.claude-plugin/plugin.json")
log "Plugin version: $PLUGIN_VERSION"
log ""

# Step 2: Setup test environment
log "[2/5] SETUP TEST ENVIRONMENT"
log "----------------------------------------"
./setup.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

# Step 3: Run campaign
log "[3/5] RUN CAMPAIGN"
log "----------------------------------------"
CAMPAIGN_START=$(date +%s)

# Capture campaign output
CAMPAIGN_LOG="$RESULTS_DIR/campaign.log"
./campaign.sh "$TEMPLATE" "$VERSION" 2>&1 | tee "$CAMPAIGN_LOG" | tee -a "$LOG_FILE"

CAMPAIGN_END=$(date +%s)
CAMPAIGN_DURATION=$((CAMPAIGN_END - CAMPAIGN_START))
log ""
log "Campaign duration: ${CAMPAIGN_DURATION}s"
log ""

# Step 4: Collect and analyze
log "[4/5] COLLECT AND ANALYZE"
log "----------------------------------------"
./collect.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

# Step 5: Deep analysis
log "[5/5] DEEP ANALYSIS"
log "----------------------------------------"

# Run detailed analysis
python3 analyze.py "$RESULTS_DIR" --detailed 2>&1 | tee -a "$LOG_FILE"
log ""

# Compare with previous same-template run if exists
PREV_RUN=$(ls -1 results/ 2>/dev/null | grep "^${TEMPLATE}-" | grep -v "${TEMPLATE}-${VERSION}$" | sort -V | tail -1)
if [ -n "$PREV_RUN" ]; then
    log "COMPARISON: $PREV_RUN -> ${TEMPLATE}-${VERSION}"
    log "----------------------------------------"
    python3 compare.py "$PREV_RUN" "${TEMPLATE}-${VERSION}" 2>&1 | tee -a "$LOG_FILE"
    log ""
fi

# Final summary
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

log "========================================"
log "EVALUATION COMPLETE"
log "========================================"
log "Template: $TEMPLATE"
log "Version: $VERSION"
log "Plugin: $PLUGIN_VERSION"
log "Duration: ${TOTAL_DURATION}s (campaign: ${CAMPAIGN_DURATION}s)"
log "Results: $RESULTS_DIR/"
log ""
log "Files:"
ls -la "$RESULTS_DIR" | tee -a "$LOG_FILE"
log ""
log "Finished: $(date)"
