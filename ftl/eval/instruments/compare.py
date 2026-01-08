#!/usr/bin/env python3
"""Generate comparison observations between two FTL runs.

Usage:
    python3 compare.py evidence/runs/anki-v10 evidence/runs/anki-v12

Produces observations, not conclusions. "Tokens increased 18%" not "performance degraded."
"""

import json
import sys
from pathlib import Path
from datetime import datetime


def load_metrics(evidence_dir: Path) -> dict:
    """Load metrics.json from evidence directory."""
    metrics_path = evidence_dir / "metrics.json"
    if not metrics_path.exists():
        print(f"Error: {metrics_path} not found")
        sys.exit(1)
    with open(metrics_path) as f:
        return json.load(f)


def delta(a: float, b: float) -> str:
    """Format delta between two values."""
    if a == 0:
        return "N/A (baseline 0)"
    diff = b - a
    pct = (diff / a) * 100
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:,.0f} ({sign}{pct:.1f}%)"


def compare_runs(run_a: dict, run_b: dict) -> str:
    """Generate comparison observations as markdown."""
    name_a = run_a["run_id"]
    name_b = run_b["run_id"]

    lines = [
        f"# Comparison: {name_a} → {name_b}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## Token Observations",
        "",
    ]

    # Token totals
    tokens_a = run_a["totals"]["tokens"]
    tokens_b = run_b["totals"]["tokens"]
    lines.append(f"**Total tokens**: {tokens_a:,} → {tokens_b:,} ({delta(tokens_a, tokens_b)})")

    # Token categories
    lines.append("")
    lines.append("**By category**:")
    for cat in ["input", "cache_read", "cache_create", "output"]:
        val_a = run_a["totals"]["tokens_by_category"][cat]
        val_b = run_b["totals"]["tokens_by_category"][cat]
        lines.append(f"  - {cat}: {val_a:,} → {val_b:,} ({delta(val_a, val_b)})")

    # Cache efficiency
    eff_a = run_a.get("cache_efficiency", 0)
    eff_b = run_b.get("cache_efficiency", 0)
    lines.append("")
    lines.append(f"**Cache efficiency**: {eff_a:.1%} → {eff_b:.1%}")

    # Agent observations
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Agent Observations")
    lines.append("")

    agents_a = run_a["totals"]["agents"]
    agents_b = run_b["totals"]["agents"]
    lines.append(f"**Agent count**: {agents_a} → {agents_b}")

    # By type
    lines.append("")
    lines.append("**By type**:")
    all_types = set(run_a["by_type"].keys()) | set(run_b["by_type"].keys())
    for atype in ["planner", "router", "builder", "learner", "synthesizer", "unknown"]:
        if atype not in all_types:
            continue
        count_a = run_a["by_type"].get(atype, {}).get("count", 0)
        count_b = run_b["by_type"].get(atype, {}).get("count", 0)
        tokens_a = run_a["by_type"].get(atype, {}).get("tokens", 0)
        tokens_b = run_b["by_type"].get(atype, {}).get("tokens", 0)

        marker = ""
        if atype == "learner" and count_a != count_b:
            marker = " ⚠️" if count_b > count_a else " ✓" if count_b < count_a else ""

        lines.append(f"  - {atype}: {count_a} → {count_b}{marker}")
        if tokens_a > 0 or tokens_b > 0:
            lines.append(f"    tokens: {tokens_a:,} → {tokens_b:,} ({delta(tokens_a, tokens_b)})")

    # Protocol fidelity
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Protocol Observations")
    lines.append("")

    fid_a = run_a.get("protocol_fidelity", {})
    fid_b = run_b.get("protocol_fidelity", {})

    def fid_status(key, name):
        val_a = fid_a.get(key, False)
        val_b = fid_b.get(key, False)
        if isinstance(val_a, bool):
            str_a = "✓" if val_a else "✗"
            str_b = "✓" if val_b else "✗"
        else:
            str_a = f"{val_a:.0%}" if val_a else "N/A"
            str_b = f"{val_b:.0%}" if val_b else "N/A"

        change = ""
        if val_a != val_b:
            if isinstance(val_b, bool):
                change = " (improved)" if val_b else " (regressed)"
            else:
                change = " (changed)"

        return f"  - {name}: {str_a} → {str_b}{change}"

    lines.append(fid_status("no_learners", "No learners in campaign"))
    lines.append(fid_status("single_planner", "Single planner"))
    lines.append(fid_status("single_synthesizer", "Single synthesizer"))
    lines.append(fid_status("router_builder_match", "Router/builder match"))
    lines.append(fid_status("router_cache_rate", "Router cache rate"))

    # Questions raised
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Questions This Raises")
    lines.append("")

    questions = []

    # Token change questions
    token_delta_pct = ((tokens_b - tokens_a) / tokens_a * 100) if tokens_a > 0 else 0
    if abs(token_delta_pct) > 15:
        direction = "increased" if token_delta_pct > 0 else "decreased"
        questions.append(f"- Tokens {direction} by {abs(token_delta_pct):.0f}%. What drove this change?")

    # Learner change
    learner_a = run_a["by_type"].get("learner", {}).get("count", 0)
    learner_b = run_b["by_type"].get("learner", {}).get("count", 0)
    if learner_a != learner_b:
        if learner_b == 0 and learner_a > 0:
            questions.append(f"- Learner count went from {learner_a} to 0. What change caused this? Is it stable?")
        elif learner_b > learner_a:
            questions.append(f"- Learner count increased ({learner_a} → {learner_b}). What broke?")

    # Cache efficiency change
    eff_delta = eff_b - eff_a
    if abs(eff_delta) > 0.05:
        direction = "improved" if eff_delta > 0 else "dropped"
        questions.append(f"- Cache efficiency {direction}. What changed in caching behavior?")

    # Synthesizer token change
    synth_a = run_a["by_type"].get("synthesizer", {}).get("tokens", 0)
    synth_b = run_b["by_type"].get("synthesizer", {}).get("tokens", 0)
    if synth_a > 0 and synth_b > 0:
        synth_delta_pct = ((synth_b - synth_a) / synth_a * 100)
        if abs(synth_delta_pct) > 30:
            direction = "increased" if synth_delta_pct > 0 else "decreased"
            questions.append(f"- Synthesizer tokens {direction} by {abs(synth_delta_pct):.0f}%. Is output quality different?")

    if not questions:
        questions.append("- No major changes observed. Is this expected stability or stagnation?")

    lines.extend(questions)

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*These are observations, not conclusions. Interpretation requires reflection.*")

    return "\n".join(lines)


def compare(evidence_a: Path, evidence_b: Path, output_path: Path = None):
    """Main comparison function."""
    metrics_a = load_metrics(evidence_a)
    metrics_b = load_metrics(evidence_b)

    comparison = compare_runs(metrics_a, metrics_b)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            f.write(comparison)
        print(f"Wrote: {output_path}")
    else:
        print(comparison)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 compare.py <evidence_a> <evidence_b> [--output <path>]")
        sys.exit(1)

    evidence_a = Path(sys.argv[1])
    evidence_b = Path(sys.argv[2])

    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[idx + 1])

    compare(evidence_a, evidence_b, output_path)
