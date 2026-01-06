#!/usr/bin/env bash
set -e

# FTL Evaluation Harness - Full Suite Runner
# Runs all 4 templates for a given version
# Usage: ./run_suite.sh v8 "optional commit message"

VERSION=$1
MSG=${2:-"eval: suite $VERSION"}

if [ -z "$VERSION" ]; then
    echo "Usage: ./run_suite.sh <version> [commit message]"
    echo "Example: ./run_suite.sh v8 'fix: enforce learner skip'"
    echo ""
    echo "This runs all 4 templates: anki, pipeline, errors, refactor"
    exit 1
fi

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$EVAL_DIR"

SUITE_LOG="$EVAL_DIR/results/suite-${VERSION}.log"
mkdir -p "$EVAL_DIR/results"

# Logging function
log() {
    echo "[$(date '+%H:%M:%S')] $1" | tee -a "$SUITE_LOG"
}

# Timer
SUITE_START=$(date +%s)

echo "" > "$SUITE_LOG"
log "=============================================="
log "FTL EVALUATION SUITE: $VERSION"
log "=============================================="
log "Started: $(date)"
log "Commit message: $MSG"
log ""

# Step 1: Propagate plugin changes (once for all templates)
log "[PROPAGATE] Updating plugin..."
log "----------------------------------------------"
./propagate.sh "$MSG" 2>&1 | tee -a "$SUITE_LOG"
log ""

PLUGIN_VERSION=$(jq -r .version "$EVAL_DIR/../.claude-plugin/plugin.json")
log "Plugin version: $PLUGIN_VERSION"
log ""

# Track results
declare -A TEMPLATE_RESULTS
declare -A TEMPLATE_DURATIONS

# Run each template
TEMPLATES="anki pipeline errors refactor"

for TEMPLATE in $TEMPLATES; do
    log "=============================================="
    log "TEMPLATE: $TEMPLATE"
    log "=============================================="

    TEMPLATE_START=$(date +%s)

    # Setup
    log "[1/3] Setup..."
    if ./setup.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$SUITE_LOG"; then
        log "Setup complete"
    else
        log "ERROR: Setup failed for $TEMPLATE"
        TEMPLATE_RESULTS[$TEMPLATE]="SETUP_FAILED"
        continue
    fi

    # Campaign
    log "[2/3] Running campaign..."
    CAMPAIGN_LOG="$EVAL_DIR/results/${TEMPLATE}-${VERSION}/campaign.log"
    mkdir -p "$(dirname "$CAMPAIGN_LOG")"
    if ./campaign.sh "$TEMPLATE" "$VERSION" 2>&1 | tee "$CAMPAIGN_LOG" | tee -a "$SUITE_LOG"; then
        log "Campaign complete"
    else
        log "ERROR: Campaign failed for $TEMPLATE"
        TEMPLATE_RESULTS[$TEMPLATE]="CAMPAIGN_FAILED"
        continue
    fi

    # Collect
    log "[3/3] Collecting results..."
    if ./collect.sh "$TEMPLATE" "$VERSION" 2>&1 | tee -a "$SUITE_LOG"; then
        log "Collection complete"
        TEMPLATE_RESULTS[$TEMPLATE]="SUCCESS"
    else
        log "ERROR: Collection failed for $TEMPLATE"
        TEMPLATE_RESULTS[$TEMPLATE]="COLLECT_FAILED"
    fi

    TEMPLATE_END=$(date +%s)
    TEMPLATE_DURATIONS[$TEMPLATE]=$((TEMPLATE_END - TEMPLATE_START))
    log "Duration: ${TEMPLATE_DURATIONS[$TEMPLATE]}s"
    log ""
done

# Cross-template analysis
log "=============================================="
log "CROSS-TEMPLATE ANALYSIS"
log "=============================================="
python3 compare_suite.py "$VERSION" 2>&1 | tee -a "$SUITE_LOG"
log ""

# Final summary
SUITE_END=$(date +%s)
SUITE_DURATION=$((SUITE_END - SUITE_START))

log "=============================================="
log "SUITE COMPLETE"
log "=============================================="
log "Version: $VERSION"
log "Plugin: $PLUGIN_VERSION"
log "Total duration: ${SUITE_DURATION}s"
log ""
log "Template Results:"
for TEMPLATE in $TEMPLATES; do
    RESULT=${TEMPLATE_RESULTS[$TEMPLATE]:-"NOT_RUN"}
    DURATION=${TEMPLATE_DURATIONS[$TEMPLATE]:-0}
    log "  $TEMPLATE: $RESULT (${DURATION}s)"
done
log ""
log "Results directories:"
ls -1d "$EVAL_DIR/results"/*-"$VERSION" 2>/dev/null | tee -a "$SUITE_LOG" || echo "  (none)"
log ""
log "Finished: $(date)"
