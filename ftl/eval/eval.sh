#!/usr/bin/env bash
set -e

# FTL Evaluation Harness
# Unified entry point for the feedback loop:
#   run → capture → reflect → learn → integrate

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
SCRATCH_DIR="$(cd "$EVAL_DIR/../../scratch" && pwd)"

show_help() {
    cat << 'EOF'
FTL Evaluation Harness

Usage: ./eval.sh <command> [args]

Commands:
  run <template> <version>       Full eval: propagate → setup → campaign → collect
  capture <run-id>               Extract evidence (metrics.json + transcript.md)
  compare <old> <new>            Delta analysis between two runs
  reflect <run-id>               Generate reflection prompts
  learn                          Review reflections, update chronicle
  integrate <learning-id>        Create FTL decision record from learning
  status                         Show available runs and evidence

Examples:
  ./eval.sh run anki v13
  ./eval.sh capture anki-v13
  ./eval.sh compare anki-v12 anki-v13
  ./eval.sh reflect anki-v13
  ./eval.sh integrate L001

Flow:
  run → capture → reflect → learn → integrate
                    ↑                    ↓
                    └──── FTL improves ──┘
EOF
}

cmd_run() {
    local template=$1
    local version=$2
    local msg=${3:-"eval: $template-$version"}

    if [ -z "$template" ] || [ -z "$version" ]; then
        echo "Usage: ./eval.sh run <template> <version> [commit message]"
        echo "Templates: anki, pipeline, errors, refactor"
        exit 1
    fi

    # Delegate to scripts/run.sh (handles full flow)
    "$EVAL_DIR/scripts/run.sh" "$template" "$version" "$msg"

    # Auto-capture evidence
    echo ""
    echo "=== Capturing evidence ==="
    cmd_capture "${template}-${version}"
}

cmd_capture() {
    local run_id=$1

    if [ -z "$run_id" ]; then
        echo "Usage: ./eval.sh capture <run-id>"
        echo "Example: ./eval.sh capture anki-v12"
        exit 1
    fi

    # Parse run_id: template-version -> version/template
    local template="${run_id%-v*}"
    local version="v${run_id##*-v}"
    local results_dir="$SCRATCH_DIR/results/$version/$template"

    if [ ! -d "$results_dir" ]; then
        echo "Error: Results not found: $results_dir"
        echo "Available versions:"
        ls -1 "$SCRATCH_DIR/results" 2>/dev/null || echo "  (none)"
        exit 1
    fi

    python3 "$EVAL_DIR/instruments/capture.py" "$results_dir"
}

cmd_compare() {
    local old=$1
    local new=$2

    if [ -z "$old" ] || [ -z "$new" ]; then
        echo "Usage: ./eval.sh compare <old-run> <new-run>"
        echo "Example: ./eval.sh compare anki-v10 anki-v12"
        exit 1
    fi

    local old_evidence="$EVAL_DIR/evidence/runs/$old"
    local new_evidence="$EVAL_DIR/evidence/runs/$new"

    # Auto-capture if needed
    if [ ! -d "$old_evidence" ]; then
        echo "Capturing evidence for $old..."
        cmd_capture "$old"
    fi
    if [ ! -d "$new_evidence" ]; then
        echo "Capturing evidence for $new..."
        cmd_capture "$new"
    fi

    local output="$EVAL_DIR/evidence/comparisons/${old}-to-${new}.md"
    mkdir -p "$EVAL_DIR/evidence/comparisons"
    python3 "$EVAL_DIR/instruments/compare.py" "$old_evidence" "$new_evidence" --output "$output"

    echo ""
    cat "$output"
}

cmd_reflect() {
    local run_id=$1

    if [ -z "$run_id" ]; then
        echo "Usage: ./eval.sh reflect <run-id>"
        echo "Example: ./eval.sh reflect anki-v12"
        exit 1
    fi

    local evidence_dir="$EVAL_DIR/evidence/runs/$run_id"

    # Auto-capture if needed
    if [ ! -d "$evidence_dir" ]; then
        echo "Capturing evidence for $run_id..."
        cmd_capture "$run_id"
    fi

    echo ""
    python3 "$EVAL_DIR/instruments/prompt.py" "$evidence_dir"
    echo ""
    echo "─────────────────────────────────────────"
    echo "Reflection files:"
    echo "  questions.md      → $EVAL_DIR/reflections/questions.md"
    echo "  understandings.md → $EVAL_DIR/reflections/understandings.md"
    echo "  surprises.md      → $EVAL_DIR/reflections/surprises.md"
    echo "  journal.md        → $EVAL_DIR/reflections/journal.md"
    echo ""
    echo "After reflection, run: ./eval.sh learn"
}

cmd_learn() {
    echo "=== Learning Flow ==="
    echo ""
    echo "Review your reflection files:"
    echo ""

    # Show recent additions to understandings.md
    if [ -f "$EVAL_DIR/reflections/understandings.md" ]; then
        echo "--- understandings.md (beliefs) ---"
        head -50 "$EVAL_DIR/reflections/understandings.md"
        echo ""
    fi

    # Show active questions
    if [ -f "$EVAL_DIR/reflections/questions.md" ]; then
        echo "--- questions.md (active) ---"
        sed -n '/^## Active/,/^## Answered/p' "$EVAL_DIR/reflections/questions.md" | head -30
        echo ""
    fi

    echo "─────────────────────────────────────────"
    echo ""
    echo "To record a learning in the chronicle:"
    echo "  1. Edit: $EVAL_DIR/chronicle.md"
    echo "  2. Add entry with Learning ID (e.g., L002)"
    echo "  3. Run: ./eval.sh integrate <learning-id>"
    echo ""
    echo "Chronicle: $EVAL_DIR/chronicle.md"
}

cmd_integrate() {
    local learning_id=$1

    if [ -z "$learning_id" ]; then
        echo "Usage: ./eval.sh integrate <learning-id>"
        echo "Example: ./eval.sh integrate L001"
        echo ""
        echo "Current learnings in chronicle:"
        grep -E "^## [0-9]{4}-[0-9]{2}-[0-9]{2}:" "$EVAL_DIR/chronicle.md" 2>/dev/null || echo "  (none)"
        echo ""
        echo "Learnings index:"
        grep -E "^\| L[0-9]+" "$EVAL_DIR/chronicle.md" 2>/dev/null || echo "  (none)"
        exit 1
    fi

    # Delegate to integrate.sh
    "$EVAL_DIR/integrate.sh" "$learning_id"
}

cmd_status() {
    echo "=== FTL Evaluation Status ==="
    echo ""

    echo "Results (raw logs):"
    if [ -d "$SCRATCH_DIR/results" ]; then
        ls -1 "$SCRATCH_DIR/results" 2>/dev/null | sed 's/^/  /' || echo "  (none)"
    else
        echo "  (none)"
    fi
    echo ""

    echo "Evidence (captured):"
    if [ -d "$EVAL_DIR/evidence/runs" ]; then
        ls -1 "$EVAL_DIR/evidence/runs" 2>/dev/null | sed 's/^/  /' || echo "  (none)"
    else
        echo "  (none)"
    fi
    echo ""

    echo "Comparisons:"
    if [ -d "$EVAL_DIR/evidence/comparisons" ]; then
        ls -1 "$EVAL_DIR/evidence/comparisons" 2>/dev/null | sed 's/^/  /' || echo "  (none)"
    else
        echo "  (none)"
    fi
    echo ""

    echo "Chronicle entries:"
    grep -E "^## [0-9]{4}-[0-9]{2}-[0-9]{2}:" "$EVAL_DIR/chronicle.md" 2>/dev/null | sed 's/^/  /' || echo "  (none)"
    echo ""

    echo "Learnings:"
    grep -E "^\| L[0-9]+" "$EVAL_DIR/chronicle.md" 2>/dev/null | sed 's/^/  /' || echo "  (none)"
}

# Main dispatch
case "${1:-}" in
    run)
        shift
        cmd_run "$@"
        ;;
    capture)
        shift
        cmd_capture "$@"
        ;;
    compare)
        shift
        cmd_compare "$@"
        ;;
    reflect)
        shift
        cmd_reflect "$@"
        ;;
    learn)
        cmd_learn
        ;;
    integrate)
        shift
        cmd_integrate "$@"
        ;;
    status)
        cmd_status
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run ./eval.sh --help for usage"
        exit 1
        ;;
esac
