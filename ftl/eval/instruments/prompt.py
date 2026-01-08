#!/usr/bin/env python3
"""Generate reflection prompts from FTL run evidence.

Usage:
    python3 prompt.py evidence/runs/anki-v12

Produces questions to consider, not scores to accept.
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


def load_reflections() -> dict:
    """Load current reflection files for context."""
    eval_dir = Path(__file__).parent.parent
    reflections = {
        "questions": "",
        "understandings": "",
    }

    questions_path = eval_dir / "reflections" / "questions.md"
    if questions_path.exists():
        reflections["questions"] = questions_path.read_text()

    understandings_path = eval_dir / "reflections" / "understandings.md"
    if understandings_path.exists():
        reflections["understandings"] = understandings_path.read_text()

    return reflections


def extract_active_questions(questions_md: str) -> list:
    """Extract active questions from questions.md."""
    active = []
    in_active = False

    for line in questions_md.split("\n"):
        if line.strip() == "## Active":
            in_active = True
            continue
        if line.strip().startswith("## ") and in_active:
            break
        if in_active and line.startswith("### "):
            active.append(line.replace("### ", "").strip())

    return active[:5]  # Top 5


def extract_beliefs(understandings_md: str) -> list:
    """Extract belief names from understandings.md."""
    beliefs = []
    for line in understandings_md.split("\n"):
        if line.startswith("## ") and not line.startswith("## Understanding"):
            beliefs.append(line.replace("## ", "").strip())
    return beliefs[:5]


def generate_prompts(metrics: dict, reflections: dict) -> str:
    """Generate reflection prompts from metrics and standing questions."""
    run_id = metrics["run_id"]
    lines = [
        f"# Reflection Prompts: {run_id}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## From the Numbers",
        "",
    ]

    # Agent composition prompt
    by_type = metrics["by_type"]
    type_counts = {t: d.get("count", 0) for t, d in by_type.items()}
    total_agents = metrics["totals"]["agents"]

    lines.append(f"**{total_agents} agents ran this session:**")
    composition = []
    for atype in ["planner", "router", "builder", "learner", "synthesizer", "unknown"]:
        if type_counts.get(atype, 0) > 0:
            marker = " ⚠️" if atype == "learner" else ""
            composition.append(f"{type_counts[atype]} {atype}{marker}")
    lines.append(", ".join(composition))
    lines.append("")
    lines.append("*Does this feel right for the objective? Were any agents unnecessary?*")
    lines.append("")

    # Cache efficiency prompt
    cache_eff = metrics.get("cache_efficiency", 0)
    lines.append(f"**Cache efficiency: {cache_eff:.1%}**")
    lines.append("")
    if cache_eff > 0.85:
        lines.append("*Good cache utilization. Is this stable across runs?*")
    elif cache_eff > 0.70:
        lines.append("*Moderate cache utilization. Where did the misses come from?*")
    else:
        lines.append("*Low cache utilization. What's being re-read unnecessarily?*")
    lines.append("")

    # Token distribution prompt
    tokens = metrics["totals"]["tokens_by_category"]
    total_tokens = metrics["totals"]["tokens"]
    lines.append(f"**Token distribution ({total_tokens:,} total):**")
    for cat in ["input", "cache_read", "cache_create", "output"]:
        val = tokens[cat]
        pct = (val / total_tokens * 100) if total_tokens > 0 else 0
        lines.append(f"  - {cat}: {val:,} ({pct:.1f}%)")
    lines.append("")
    lines.append("*Where was attention spent? Was it well-placed?*")
    lines.append("")

    # Per-type token prompts
    lines.append("**Token by agent type:**")
    for atype in ["planner", "router", "builder", "synthesizer"]:
        if atype in by_type:
            atype_tokens = by_type[atype].get("tokens", 0)
            if atype_tokens > 0:
                lines.append(f"  - {atype}: {atype_tokens:,}")
    lines.append("")

    # Specific prompts based on data
    if by_type.get("synthesizer", {}).get("tokens", 0) > 400000:
        synth_tokens = by_type["synthesizer"]["tokens"]
        lines.append(f"*Synthesizer used {synth_tokens:,} tokens. Was the output proportionally valuable?*")
        lines.append("")

    if type_counts.get("learner", 0) > 0:
        learner_tokens = by_type["learner"].get("tokens", 0)
        lines.append(f"*⚠️ {type_counts['learner']} learners spawned ({learner_tokens:,} tokens). This shouldn't happen in campaigns. What went wrong?*")
        lines.append("")

    if type_counts.get("unknown", 0) > 0:
        lines.append(f"*{type_counts['unknown']} agents couldn't be classified. Look at their transcripts—what are they?*")
        lines.append("")

    # Protocol fidelity prompts
    fidelity = metrics.get("protocol_fidelity", {})
    lines.append("---")
    lines.append("")
    lines.append("## From Protocol Observations")
    lines.append("")

    if not fidelity.get("no_learners", True):
        lines.append("- **Learners were spawned.** Review the Two Workflows section. What caused the category error?")
    if not fidelity.get("router_builder_match", True):
        router_count = type_counts.get("router", 0)
        builder_count = type_counts.get("builder", 0)
        lines.append(f"- **Router/builder mismatch** ({router_count} vs {builder_count}). What caused the divergence?")
    if fidelity.get("router_cache_rate", 0) < 1.0:
        rate = fidelity["router_cache_rate"]
        lines.append(f"- **Router cache rate: {rate:.0%}.** Which routers missed cache? Were they first in session?")

    all_ok = all([
        fidelity.get("no_learners", True),
        fidelity.get("single_planner", True),
        fidelity.get("single_synthesizer", True),
        fidelity.get("router_builder_match", True),
    ])
    if all_ok:
        lines.append("- Protocol adherence looks clean. Is this reliable or lucky?")

    lines.append("")

    # Standing questions
    active_questions = extract_active_questions(reflections["questions"])
    if active_questions:
        lines.append("---")
        lines.append("")
        lines.append("## Standing Questions to Consider")
        lines.append("")
        lines.append("*From questions.md—does this run shed light on any of these?*")
        lines.append("")
        for q in active_questions:
            lines.append(f"- {q}")
        lines.append("")

    # Beliefs to challenge
    beliefs = extract_beliefs(reflections["understandings"])
    if beliefs:
        lines.append("---")
        lines.append("")
        lines.append("## Beliefs to Test")
        lines.append("")
        lines.append("*From understandings.md—did anything in this run confirm or challenge these?*")
        lines.append("")
        for belief in beliefs:
            lines.append(f"- {belief}")
        lines.append("")

    # Meta prompts
    lines.append("---")
    lines.append("")
    lines.append("## Open Reflection")
    lines.append("")
    lines.append("- What surprised you about this run?")
    lines.append("- What would you do differently next time?")
    lines.append("- What are you still confused about?")
    lines.append("- Did you learn anything new?")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*These are prompts, not tests. The goal is noticing, not scoring.*")

    return "\n".join(lines)


def prompt(evidence_dir: Path):
    """Main prompt generation function."""
    metrics = load_metrics(evidence_dir)
    reflections = load_reflections()
    prompts = generate_prompts(metrics, reflections)
    print(prompts)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 prompt.py <evidence_dir>")
        sys.exit(1)

    evidence_dir = Path(sys.argv[1])
    prompt(evidence_dir)
