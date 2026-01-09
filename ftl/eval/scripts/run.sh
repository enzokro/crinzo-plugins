#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Full Eval Loop for Single Template
# Usage: ./scripts/run.sh anki v8 "optional commit message"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EVAL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SCRATCH_DIR="$(cd "$EVAL_DIR/../../scratch" && pwd)"

TEMPLATE=$1
VERSION=$2
MSG=${3:-"eval: $TEMPLATE-$VERSION"}

if [ -z "$TEMPLATE" ] || [ -z "$VERSION" ]; then
    echo "Usage: ./scripts/run.sh <template> <version> [commit message]"
    echo "Templates: anki, pipeline, errors, refactor"
    echo "Example: ./scripts/run.sh anki v8 'fix: enforce learner skip'"
    echo ""
    echo "For full suite: ./scripts/run_suite.sh v8"
    exit 1
fi

cd "$SCRIPT_DIR"

RESULTS_DIR="$SCRATCH_DIR/results/${VERSION}/${TEMPLATE}"
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
log "[1/4] PROPAGATE PLUGIN"
log "----------------------------------------"
./propagate.sh "$MSG" 2>&1 | tee -a "$LOG_FILE"
log ""

# Capture plugin version
PLUGIN_VERSION=$(jq -r .version "$EVAL_DIR/../.claude-plugin/plugin.json")
log "Plugin version: $PLUGIN_VERSION"
log ""

# Step 2: Setup test environment
log "[2/4] SETUP TEST ENVIRONMENT"
log "----------------------------------------"
./setup.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

# Step 3: Run campaign
log "[3/4] RUN CAMPAIGN"
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

# Step 4: Collect agent logs
log "[4/4] COLLECT AGENT LOGS"
log "----------------------------------------"
./collect.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$LOG_FILE"
log ""

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
log "Next: ./eval.sh capture ${TEMPLATE}-${VERSION}"
log ""
log "Files:"
ls -la "$RESULTS_DIR" | tee -a "$LOG_FILE"
log ""
log "Finished: $(date)"
