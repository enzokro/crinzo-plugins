#!/bin/bash
# Meta-improvement loop: Execute, Capture, Assess, Learn
# Usage: ./meta_eval.sh <template> <version> [--force]
# Example: ./meta_eval.sh anki v13
#
# Outputs everything needed for rigorous learning:
# - Full metrics with loop signals
# - Complete transcript for reasoning review
# - Per-agent token variance analysis
# - Behavioral pattern detection (TDD, error diagnosis)
# - Comparison to previous run
# - Suggested learnings for understandings.md

set -e

# Parse --force flag
FORCE=false
for arg in "$@"; do
    [[ "$arg" == "--force" ]] && FORCE=true
done

TEMPLATE="${1:?Usage: $0 <template> <version> [--force]}"
VERSION="${2:?Usage: $0 <template> <version> [--force]}"

# Validate: catch old syntax like "anki-v13" as first arg
if [[ "$TEMPLATE" == *-v* ]]; then
    echo "Error: Old syntax detected. Use: $0 <template> <version>"
    echo "  Wrong: $0 anki-v13"
    echo "  Right: $0 anki v13"
    exit 1
fi

# Validate: version should start with 'v'
if [[ "$VERSION" != v* ]]; then
    echo "Error: Version should start with 'v' (e.g., v13)"
    echo "Usage: $0 <template> <version> [--force]"
    exit 1
fi

RUN_ID="${TEMPLATE}-${VERSION}"

EVAL_DIR="$(cd "$(dirname "$0")" && pwd)"
RESULTS_DIR="$EVAL_DIR/results/$RUN_ID"
EVIDENCE_DIR="$EVAL_DIR/evidence/runs/$RUN_ID"
REFLECTIONS_DIR="$EVAL_DIR/reflections"

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           META-IMPROVEMENT LOOP: $RUN_ID"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ============================================
# Phase 1: Execute Campaign
# ============================================
echo "━━━ Phase 1: Execute Campaign ━━━"

if [[ -d "$RESULTS_DIR" && "$FORCE" != "true" ]]; then
    echo "✓ Results exist at $RESULTS_DIR (use --force to re-run)"
else
    [[ -d "$RESULTS_DIR" ]] && rm -rf "$RESULTS_DIR"
    "$EVAL_DIR/scripts/run.sh" "$TEMPLATE" "$VERSION"
fi

# ============================================
# Phase 2: Capture Evidence
# ============================================
echo ""
echo "━━━ Phase 2: Capture Evidence ━━━"

python3 "$EVAL_DIR/instruments/capture.py" "$RESULTS_DIR" --output "$EVIDENCE_DIR"

# ============================================
# Phase 3: Loop Stability Signals
# ============================================
echo ""
echo "━━━ Phase 3: Loop Stability Signals ━━━"

python3 - "$EVIDENCE_DIR" << 'SIGNALS_EOF'
import json
import sys

evidence_dir = sys.argv[1]
with open(f"{evidence_dir}/metrics.json") as f:
    d = json.load(f)

ls = d["loop_signals"]
pf = d["protocol_fidelity"]
t = d["totals"]

print("┌─────────────────────────────────────┐")
print("│ LOOP SIGNALS                        │")
print("├─────────────────────────────────────┤")
print(f"│ Tasks complete:      {ls['tasks_complete']:3d}            │")
print(f"│ Tasks failed:        {ls['tasks_failed']:3d}            │")
print(f"│ Fallback used:       {ls['fallback_used']:3d}            │")
print(f"│ Cache effective:     {pf['router_cache_effective']:3.0%}           │")
print(f"│ No learners:         {'Yes' if pf['no_learners'] else 'NO!':3s}            │")
print("├─────────────────────────────────────┤")
print(f"│ Total tokens:    {t['tokens']:>12,}      │")
print(f"│ Cache efficiency:    {d['cache_efficiency']:5.1%}         │")
print(f"│ Agents:              {t['agents']:3d}            │")
print("└─────────────────────────────────────┘")

# Issues
issues = []
if ls["tasks_failed"] > 0:
    issues.append(f"FAILED: {ls['tasks_failed']} tasks")
if ls["fallback_used"] > 0:
    issues.append(f"FALLBACK: {ls['fallback_used']} agents")
if pf["router_cache_effective"] == 0:
    issues.append("CACHE: not warming")
if not pf["no_learners"]:
    issues.append("LEARNERS: spawned (protocol violation)")

if issues:
    print()
    print("⚠️  ISSUES DETECTED:")
    for issue in issues:
        print(f"   • {issue}")
    # Don't exit - continue to show full analysis
else:
    print()
    print("✓ No structural issues detected")
SIGNALS_EOF

# Capture whether there were issues (for final exit code)
# Use || true to prevent set -e from exiting
python3 - "$EVIDENCE_DIR" << 'CHECK_EOF' || true
import json, sys
with open(f"{sys.argv[1]}/metrics.json") as f:
    d = json.load(f)
ls = d["loop_signals"]
pf = d["protocol_fidelity"]
has_issues = ls["tasks_failed"] > 0 or ls["fallback_used"] > 0 or pf["router_cache_effective"] == 0 or not pf["no_learners"]
sys.exit(1 if has_issues else 0)
CHECK_EOF
# Re-check for final status (since || true absorbed the exit code)
SIGNALS_STATUS=$(python3 -c "
import json
with open('$EVIDENCE_DIR/metrics.json') as f:
    d = json.load(f)
ls = d['loop_signals']
pf = d['protocol_fidelity']
has_issues = ls['tasks_failed'] > 0 or ls['fallback_used'] > 0 or pf['router_cache_effective'] == 0 or not pf['no_learners']
print(1 if has_issues else 0)
")

# ============================================
# Phase 4: Per-Agent Analysis
# ============================================
echo ""
echo "━━━ Phase 4: Per-Agent Analysis ━━━"

python3 - "$EVIDENCE_DIR" << 'AGENTS_EOF'
import json
import sys

evidence_dir = sys.argv[1]
with open(f"{evidence_dir}/metrics.json") as f:
    d = json.load(f)

agents = d["agents"]

# Sort by spawn order
agents_sorted = sorted(agents, key=lambda a: a.get("spawn_order", 999))

print("┌───────┬────────────┬─────┬───────────┬──────────┬─────────┐")
print("│ Order │ Type       │Task │ Tokens    │ Outcome  │ Flags   │")
print("├───────┼────────────┼─────┼───────────┼──────────┼─────────┤")

for a in agents_sorted:
    order = a.get("spawn_order", "?")
    atype = a["type"][:10]
    task = a.get("task_id") or "-"
    tokens = a["tokens"]["total"]
    outcome = a.get("task_outcome") or "-"

    flags = []
    if a.get("used_fallback"):
        flags.append("fb")
    if a.get("cache_had_content"):
        flags.append("cache")

    outcome_display = "ok" if outcome == "complete" else ("FAIL" if outcome == "failed" else "-")
    flags_str = " ".join(flags)

    print(f"│ {order:>5} │ {atype:<10} │ {task:>3} │ {tokens:>9,} │ {outcome_display:^8} │ {flags_str:<7} │")

print("└───────┴────────────┴─────┴───────────┴──────────┴─────────┘")

# Token variance analysis
builders = [a for a in agents if a["type"] == "builder"]
if len(builders) > 1:
    tokens_list = [a["tokens"]["total"] for a in builders]
    min_t, max_t = min(tokens_list), max(tokens_list)
    variance = max_t / min_t if min_t > 0 else 0

    print()
    print(f"Token Variance (builders): {variance:.1f}x (min: {min_t:,}, max: {max_t:,})")

    if variance > 3:
        print("  ⚠️  High variance - investigate efficiency patterns")
        # Find extremes
        min_builder = min(builders, key=lambda a: a["tokens"]["total"])
        max_builder = max(builders, key=lambda a: a["tokens"]["total"])
        print(f"  Efficient: task-{min_builder.get('task_id', '?')} ({min_builder['tokens']['total']:,})")
        print(f"  Costly:    task-{max_builder.get('task_id', '?')} ({max_builder['tokens']['total']:,})")
AGENTS_EOF

# ============================================
# Phase 5: Behavioral Pattern Detection
# ============================================
echo ""
echo "━━━ Phase 5: Behavioral Patterns ━━━"

echo ""
echo "TDD Adoption:"
TDD_COUNT=$(grep -c "test-first\|write tests first" "$EVIDENCE_DIR/transcript.md" 2>/dev/null || echo "0")
echo "  $TDD_COUNT instances of test-first behavior"

echo ""
echo "Error Diagnosis (root cause identification):"
grep -i "the issue is\|the problem is\|root cause\|because.*fails" "$EVIDENCE_DIR/transcript.md" 2>/dev/null | head -3 || echo "  (none found)"

echo ""
echo "Fallback/Limitation mentions:"
grep -i "not available\|fallback\|manually\|library scripts" "$EVIDENCE_DIR/transcript.md" 2>/dev/null | head -3 || echo "  (none found)"

# ============================================
# Phase 6: Full Transcript (for deep review)
# ============================================
echo ""
echo "━━━ Phase 6: Full Transcript ━━━"
echo ""
cat "$EVIDENCE_DIR/transcript.md"

# ============================================
# Phase 7: Compare to Previous Run
# ============================================
PREV_RUN=$(ls -1d "$EVAL_DIR/evidence/runs"/*-v* 2>/dev/null | grep -v "$RUN_ID" | sort -V | tail -1)

if [[ -n "$PREV_RUN" && -f "$PREV_RUN/metrics.json" ]]; then
    echo ""
    echo "━━━ Phase 7: Comparison to $(basename $PREV_RUN) ━━━"

    python3 - "$PREV_RUN" "$EVIDENCE_DIR" << 'COMPARE_EOF'
import json
import sys

prev_dir, curr_dir = sys.argv[1], sys.argv[2]

with open(f"{prev_dir}/metrics.json") as f:
    prev = json.load(f)
with open(f"{curr_dir}/metrics.json") as f:
    curr = json.load(f)

prev_t = prev["totals"]["tokens"]
curr_t = curr["totals"]["tokens"]
delta = curr_t - prev_t
pct = delta / prev_t if prev_t > 0 else 0

print("┌─────────────────────────────────────────┐")
print("│ COMPARISON                              │")
print("├─────────────────────────────────────────┤")
print(f"│ Tokens:  {prev_t:>10,} → {curr_t:>10,}    │")
print(f"│ Delta:   {delta:>+10,} ({pct:>+6.1%})        │")
print("└─────────────────────────────────────────┘")

# Only compare loop_signals if both runs have them
prev_ls = prev.get("loop_signals", {})
curr_ls = curr.get("loop_signals", {})
prev_pf = prev.get("protocol_fidelity", {})
curr_pf = curr.get("protocol_fidelity", {})

if prev_ls and curr_ls:
    print()
    print(f"Complete: {prev_ls.get('tasks_complete', '?'):>3} → {curr_ls.get('tasks_complete', '?'):>3}")
    print(f"Failed:   {prev_ls.get('tasks_failed', '?'):>3} → {curr_ls.get('tasks_failed', '?'):>3}")
    print(f"Fallback: {prev_ls.get('fallback_used', '?'):>3} → {curr_ls.get('fallback_used', '?'):>3}")

    prev_cache = prev_pf.get('router_cache_effective', 0)
    curr_cache = curr_pf.get('router_cache_effective', 0)
    print(f"Cache:    {prev_cache:>3.0%} → {curr_cache:>3.0%}")
else:
    print()
    print("(Previous run has different metrics format)")

# Improvement assessment
improvements = []
regressions = []

if curr_t < prev_t:
    improvements.append(f"Token reduction: {-delta:,} ({-pct:.1%})")
elif curr_t > prev_t * 1.1:
    regressions.append(f"Token increase: {delta:,} ({pct:.1%})")

if prev_ls and curr_ls:
    if curr_ls.get("tasks_failed", 0) < prev_ls.get("tasks_failed", 0):
        improvements.append("Fewer failed tasks")
    elif curr_ls.get("tasks_failed", 0) > prev_ls.get("tasks_failed", 0):
        regressions.append("More failed tasks")

    if curr_pf.get("router_cache_effective", 0) > prev_pf.get("router_cache_effective", 0):
        improvements.append("Cache warming improved")

if improvements:
    print()
    print("IMPROVEMENTS:")
    for i in improvements:
        print(f"   + {i}")

if regressions:
    print()
    print("REGRESSIONS:")
    for r in regressions:
        print(f"   - {r}")
COMPARE_EOF
fi

# ============================================
# Phase 8: Suggested Learnings
# ============================================
echo ""
echo "━━━ Phase 8: Suggested Learnings ━━━"

python3 - "$EVIDENCE_DIR" << 'LEARNINGS_EOF'
import json
import sys

evidence_dir = sys.argv[1]
with open(f"{evidence_dir}/metrics.json") as f:
    d = json.load(f)

ls = d["loop_signals"]
pf = d["protocol_fidelity"]

print("Based on this run, consider adding to understandings.md:")
print()

if pf["no_learners"]:
    print("## Confirm L001: Structural framing continues to work")
    print("Evidence: 0 learners spawned in this campaign")
    print()

if pf["router_cache_effective"] == 0:
    print("## Question: Why isn't cache warming?")
    print("All routers report 'no cache available'. Is this expected for first-run?")
    print("Or is cache population broken in router prompts?")
    print()

if ls["fallback_used"] > 0:
    agents_fb = d["loop_signals"]["agents_with_fallback"]
    print(f"## Issue: {ls['fallback_used']} agent(s) used fallback")
    print(f"Agents: {agents_fb}")
    print("Investigate: What environmental limitation was hit?")
    print()

builders = [a for a in d["agents"] if a["type"] == "builder"]
if len(builders) > 1:
    tokens = [a["tokens"]["total"] for a in builders]
    variance = max(tokens) / min(tokens) if min(tokens) > 0 else 0
    if variance > 5:
        print(f"## Question: Why {variance:.1f}x token variance across builders?")
        print("Same model, same campaign. What drove the difference?")
        print("Examine: task complexity? exploration depth? error recovery?")
        print()

print("---")
print("Copy relevant learnings to: reflections/understandings.md")
LEARNINGS_EOF

# ============================================
# Summary
# ============================================
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    RUN COMPLETE                              ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║ Evidence:    $EVIDENCE_DIR"
echo "║ Metrics:     $EVIDENCE_DIR/metrics.json"
echo "║ Transcript:  $EVIDENCE_DIR/transcript.md"
echo "║ Reflections: $REFLECTIONS_DIR/"
echo "╚══════════════════════════════════════════════════════════════╝"

if [[ $SIGNALS_STATUS -ne 0 ]]; then
    echo ""
    echo "⚠️  Issues detected - review and improve before next run"
    exit 1
fi
