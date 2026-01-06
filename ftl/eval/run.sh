#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Full Eval Loop
# Usage: ./run.sh v8 "optional commit message"

VERSION=$1
MSG=${2:-"eval: $VERSION"}

if [ -z "$VERSION" ]; then
    echo "Usage: ./run.sh <version> [commit message]"
    echo "Example: ./run.sh v8 'fix: enforce learner skip'"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EVAL_DIR"

RESULTS_DIR="$EVAL_DIR/results/$VERSION"
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
log "FTL EVALUATION: $VERSION"
log "========================================"
log "Started: $(date)"
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
./setup.sh "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

# Step 3: Run campaign
log "[3/5] RUN CAMPAIGN"
log "----------------------------------------"
CAMPAIGN_START=$(date +%s)

# Capture campaign output
CAMPAIGN_LOG="$RESULTS_DIR/campaign.log"
./campaign.sh "$VERSION" 2>&1 | tee "$CAMPAIGN_LOG" | tee -a "$LOG_FILE"

CAMPAIGN_END=$(date +%s)
CAMPAIGN_DURATION=$((CAMPAIGN_END - CAMPAIGN_START))
log ""
log "Campaign duration: ${CAMPAIGN_DURATION}s"
log ""

# Step 4: Collect and analyze
log "[4/5] COLLECT AND ANALYZE"
log "----------------------------------------"
./collect.sh "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

# Step 5: Deep analysis
log "[5/5] DEEP ANALYSIS"
log "----------------------------------------"

# Run detailed analysis
python3 analyze.py "$RESULTS_DIR" --detailed 2>&1 | tee -a "$LOG_FILE"
log ""

# Compare with previous if exists
PREV_VERSION=$(ls -1 results/ 2>/dev/null | grep -v "^$VERSION$" | sort -V | tail -1)
if [ -n "$PREV_VERSION" ]; then
    log "COMPARISON: $PREV_VERSION -> $VERSION"
    log "----------------------------------------"
    python3 compare.py "$PREV_VERSION" "$VERSION" 2>&1 | tee -a "$LOG_FILE"
    log ""
fi

# Final summary
END_TIME=$(date +%s)
TOTAL_DURATION=$((END_TIME - START_TIME))

log "========================================"
log "EVALUATION COMPLETE"
log "========================================"
log "Version: $VERSION"
log "Plugin: $PLUGIN_VERSION"
log "Duration: ${TOTAL_DURATION}s (campaign: ${CAMPAIGN_DURATION}s)"
log "Results: $RESULTS_DIR/"
log ""
log "Files:"
ls -la "$RESULTS_DIR" | tee -a "$LOG_FILE"
log ""
log "Finished: $(date)"
