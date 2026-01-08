#!/usr/bin/env python3
"""Cognitive trace analyzer for FTL evaluation runs.

Classifies reasoning traces as explore/action/neutral and computes
cognitive efficiency metrics to identify protocol improvements.

Usage:
    python3 cognition.py evidence/runs/anki-v17
    python3 cognition.py evidence/runs/anki-v13 evidence/runs/anki-v17

Produces:
    - cognition.json: Per-agent cognitive metrics
    - cognitive_recommendations.md: Protocol change recommendations
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from statistics import mean, stdev


# Patterns indicating exploratory thinking (high entropy)
EXPLORE_PATTERNS = [
    r"let me (look|check|see|examine|explore|read|review)",
    r"need to understand",
    r"what (is|are|does|would)",
    r"how (do|does|is|can|should)",
    r"first.*(check|look|see|examine)",
    r"let's (see|check|look|examine)",
    r"i('ll| will) (look|check|see|examine|explore)",
    r"to understand",
    r"figure out",
]

# Patterns indicating action-oriented thinking (high epiplexity)
ACTION_PATTERNS = [
    r"i('ll| will) (implement|write|create|add|build|make)",
    r"now i have.*(clear|complete|full)",
    r"the (task|path|goal) is",
    r"status:\s*(complete|done)",
    r"verification (passed|complete|succeeded)",
    r"i('ll| will) (run|execute|verify)",
    r"now (let me |i('ll| will ))?(implement|write|create)",
    r"proceeding (with|to)",
    r"executing",
]


def classify_thinking(text: str) -> str:
    """Classify a thinking trace as explore, action, or neutral."""
    if not text:
        return "neutral"

    text_lower = text.lower()

    explore_score = sum(1 for p in EXPLORE_PATTERNS if re.search(p, text_lower))
    action_score = sum(1 for p in ACTION_PATTERNS if re.search(p, text_lower))

    if explore_score > action_score:
        return "explore"
    elif action_score > explore_score:
        return "action"
    return "neutral"


def max_consecutive(items: list, target: str) -> int:
    """Find maximum consecutive occurrences of target in list."""
    max_count = 0
    current_count = 0

    for item in items:
        if item == target:
            current_count += 1
            max_count = max(max_count, current_count)
        else:
            current_count = 0

    return max_count


def analyze_cognition(agent: dict) -> dict:
    """Compute cognitive metrics from reasoning traces."""
    traces = agent.get("reasoning_trace", [])

    if not traces:
        return {
            "trace_count": 0,
            "explore_count": 0,
            "action_count": 0,
            "neutral_count": 0,
            "action_explore_ratio": None,
            "first_action_position": -1,
            "explore_burst_max": 0,
            "terminal_class": None,
            "classifications": [],
        }

    classifications = [classify_thinking(t.get("thinking", "")) for t in traces]

    explore_count = classifications.count("explore")
    action_count = classifications.count("action")
    neutral_count = classifications.count("neutral")

    # Action/explore ratio (None if no explore)
    if explore_count > 0:
        ratio = action_count / explore_count
    elif action_count > 0:
        ratio = float("inf")  # All action, no explore
    else:
        ratio = None  # All neutral

    # First action position (-1 if no action)
    first_action = -1
    for i, c in enumerate(classifications):
        if c == "action":
            first_action = i
            break

    return {
        "trace_count": len(traces),
        "explore_count": explore_count,
        "action_count": action_count,
        "neutral_count": neutral_count,
        "action_explore_ratio": ratio if ratio != float("inf") else 999.0,
        "first_action_position": first_action,
        "explore_burst_max": max_consecutive(classifications, "explore"),
        "terminal_class": classifications[-1] if classifications else None,
        "classifications": classifications,
    }


def assess_cognition(metrics: dict, agent_type: str) -> str:
    """Generate assessment string for cognitive metrics."""
    if metrics["trace_count"] == 0:
        return "no traces"

    ratio = metrics["action_explore_ratio"]
    first_action = metrics["first_action_position"]
    burst = metrics["explore_burst_max"]

    assessments = []

    # Ratio assessment
    if ratio is None:
        assessments.append("neutral-only")
    elif ratio >= 2.0:
        assessments.append("action-heavy (optimal)")
    elif ratio >= 1.0:
        assessments.append("balanced")
    elif ratio > 0:
        assessments.append("explore-heavy (inefficient)")
    else:
        assessments.append("all-explore (high entropy)")

    # First action assessment
    if first_action == 0:
        assessments.append("immediate action")
    elif first_action == -1:
        assessments.append("no action traces")
    elif first_action > 2:
        assessments.append(f"late action (pos {first_action})")

    # Burst assessment
    if burst > 2:
        assessments.append(f"explore burst ({burst})")

    return "; ".join(assessments)


def generate_recommendations(agent_type: str, metrics: dict) -> list:
    """Generate protocol recommendations from cognitive metrics."""
    recs = []

    ratio = metrics["action_explore_ratio"]
    first_action = metrics["first_action_position"]
    burst = metrics["explore_burst_max"]

    # High explore ratio → add "act first" guidance
    if ratio is not None and ratio < 1.0:
        recs.append({
            "type": "protocol",
            "agent": f"{agent_type}.md",
            "section": "Core Discipline",
            "change": 'Add: "Act within first 3 tool calls. Do not explore to understand; understand to act."',
            "rationale": f"explore:action ratio {metrics['explore_count']}:{metrics['action_count']}",
            "priority": "high",
        })

    # Late first action → add explicit action trigger
    if first_action > 2:
        recs.append({
            "type": "protocol",
            "agent": f"{agent_type}.md",
            "section": "Execution",
            "change": 'Add: "After reading workspace/context, Write or Edit immediately."',
            "rationale": f"first action at position {first_action}",
            "priority": "medium",
        })

    # Explore bursts → add burst-breaking guidance
    if burst > 2:
        recs.append({
            "type": "protocol",
            "agent": f"{agent_type}.md",
            "section": "Constraints",
            "change": 'Add: "Maximum 2 consecutive Reads before Write/Edit."',
            "rationale": f"explore burst of {burst} consecutive traces",
            "priority": "medium",
        })

    return recs


def load_metrics(evidence_dir: Path) -> dict:
    """Load metrics.json from evidence directory."""
    metrics_path = evidence_dir / "metrics.json"
    if not metrics_path.exists():
        print(f"Error: {metrics_path} not found")
        sys.exit(1)
    with open(metrics_path) as f:
        return json.load(f)


def analyze_run(evidence_dir: Path) -> dict:
    """Analyze cognitive patterns in a single run."""
    metrics = load_metrics(evidence_dir)
    agents = sorted(metrics["agents"], key=lambda a: a.get("spawn_order", 99))

    results = []
    all_recommendations = []

    for agent in agents:
        cognition = analyze_cognition(agent)
        assessment = assess_cognition(cognition, agent["type"])
        recommendations = generate_recommendations(agent["type"], cognition)

        results.append({
            "step": agent.get("spawn_order"),
            "type": agent["type"],
            "task": agent.get("task_id"),
            "tokens": agent["tokens"]["total"],
            "cognition": {k: v for k, v in cognition.items() if k != "classifications"},
            "trace_pattern": "".join(
                "E" if c == "explore" else "A" if c == "action" else "."
                for c in cognition["classifications"]
            ),
            "assessment": assessment,
        })

        all_recommendations.extend(recommendations)

    # Dedupe recommendations by (agent, section)
    seen = set()
    unique_recs = []
    for rec in all_recommendations:
        key = (rec["agent"], rec["section"])
        if key not in seen:
            seen.add(key)
            unique_recs.append(rec)

    return {
        "run_id": metrics["run_id"],
        "computed_at": datetime.now().isoformat(),
        "agents": results,
        "recommendations": unique_recs,
        "summary": {
            "total_agents": len(results),
            "avg_action_ratio": mean([
                a["cognition"]["action_explore_ratio"]
                for a in results
                if a["cognition"]["action_explore_ratio"] is not None
                and a["cognition"]["action_explore_ratio"] < 100
            ]) if results else 0,
            "agents_with_recommendations": len(set(r["agent"] for r in unique_recs)),
        },
    }


def compare_runs(evidence_a: Path, evidence_b: Path) -> dict:
    """Compare cognitive patterns between two runs."""
    result_a = analyze_run(evidence_a)
    result_b = analyze_run(evidence_b)

    # Match agents by spawn_order
    agents_a = {a["step"]: a for a in result_a["agents"]}
    agents_b = {a["step"]: a for a in result_b["agents"]}

    comparisons = []
    for step in sorted(set(agents_a.keys()) | set(agents_b.keys())):
        a = agents_a.get(step)
        b = agents_b.get(step)

        if a and b:
            ratio_a = a["cognition"]["action_explore_ratio"]
            ratio_b = b["cognition"]["action_explore_ratio"]

            # Handle inf/None
            ratio_a_safe = ratio_a if ratio_a is not None and ratio_a < 100 else None
            ratio_b_safe = ratio_b if ratio_b is not None and ratio_b < 100 else None

            comparisons.append({
                "step": step,
                "type": a["type"],
                "task": a.get("task"),
                "a": {
                    "tokens": a["tokens"],
                    "ratio": ratio_a_safe,
                    "pattern": a["trace_pattern"],
                },
                "b": {
                    "tokens": b["tokens"],
                    "ratio": ratio_b_safe,
                    "pattern": b["trace_pattern"],
                },
                "token_delta": (b["tokens"] - a["tokens"]) / a["tokens"] if a["tokens"] > 0 else 0,
                "ratio_improved": (ratio_b_safe or 0) > (ratio_a_safe or 0),
            })

    return {
        "run_a": result_a["run_id"],
        "run_b": result_b["run_id"],
        "computed_at": datetime.now().isoformat(),
        "comparisons": comparisons,
        "recommendations": result_b["recommendations"],
    }


def generate_markdown(result: dict, comparison: dict = None) -> str:
    """Generate markdown report."""
    lines = []

    if comparison:
        lines.append(f"# Cognitive Analysis: {comparison['run_a']} → {comparison['run_b']}")
    else:
        lines.append(f"# Cognitive Analysis: {result['run_id']}")

    lines.extend(["", f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*", "", "---", ""])

    if comparison:
        lines.append("## Agent Comparison")
        lines.append("")
        lines.append("| Step | Type | Task | A Pattern | B Pattern | Token Δ | Ratio Improved |")
        lines.append("|------|------|------|-----------|-----------|---------|----------------|")

        for c in comparison["comparisons"]:
            task = c["task"] or "-"
            delta = f"{c['token_delta']:+.0%}"
            improved = "Yes" if c["ratio_improved"] else "No"
            lines.append(f"| {c['step']} | {c['type']} | {task} | `{c['a']['pattern']}` | `{c['b']['pattern']}` | {delta} | {improved} |")

        lines.extend(["", "**Legend**: E=explore, A=action, .=neutral", ""])
    else:
        lines.append("## Agents")
        lines.append("")

        for a in result["agents"]:
            task = f"task {a['task']}" if a["task"] else ""
            lines.append(f"### Step {a['step']}: {a['type']} {task}")
            lines.append("")
            lines.append(f"**Tokens**: {a['tokens']:,}")
            lines.append(f"**Pattern**: `{a['trace_pattern']}`")
            lines.append(f"**Assessment**: {a['assessment']}")

            cog = a["cognition"]
            lines.append(f"**Metrics**: explore={cog['explore_count']} action={cog['action_count']} ratio={cog['action_explore_ratio']}")
            lines.append("")

    # Recommendations
    recs = comparison["recommendations"] if comparison else result["recommendations"]
    if recs:
        lines.extend(["---", "", "## Recommendations", ""])

        for rec in recs:
            lines.append(f"### {rec['agent']} → {rec['section']}")
            lines.append("")
            lines.append(f"**Priority**: {rec['priority']}")
            lines.append(f"**Change**: {rec['change']}")
            lines.append(f"**Rationale**: {rec['rationale']}")
            lines.append("")
    else:
        lines.extend(["---", "", "## Recommendations", "", "*No recommendations - cognitive patterns are optimal.*", ""])

    return "\n".join(lines)


def analyze(evidence_dirs: list[Path], output_dir: Path = None):
    """Main analysis function."""
    if len(evidence_dirs) == 1:
        result = analyze_run(evidence_dirs[0])
        comparison = None
        output_dir = output_dir or evidence_dirs[0]
    else:
        result = analyze_run(evidence_dirs[1])
        comparison = compare_runs(evidence_dirs[0], evidence_dirs[1])
        output_dir = output_dir or evidence_dirs[1]

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON
    json_path = output_dir / "cognition.json"
    with open(json_path, "w") as f:
        json.dump(comparison or result, f, indent=2)
    print(f"Wrote: {json_path}")

    # Write markdown
    md_path = output_dir / "cognitive_recommendations.md"
    with open(md_path, "w") as f:
        f.write(generate_markdown(result, comparison))
    print(f"Wrote: {md_path}")

    # Print summary
    print()
    if comparison:
        print(f"{comparison['run_a']} → {comparison['run_b']}")
        improved = sum(1 for c in comparison["comparisons"] if c["ratio_improved"])
        print(f"Agents with improved ratio: {improved}/{len(comparison['comparisons'])}")
    else:
        print(f"{result['run_id']}")
        print(f"Average action/explore ratio: {result['summary']['avg_action_ratio']:.1f}")

    recs = comparison["recommendations"] if comparison else result["recommendations"]
    if recs:
        print(f"\nRecommendations ({len(recs)}):")
        for rec in recs:
            print(f"  - {rec['agent']}: {rec['change'][:50]}...")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 cognition.py <evidence_dir> [<evidence_dir_2>] [--output <dir>]")
        sys.exit(1)

    evidence_dirs = []
    output_dir = None

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--output" and i + 1 < len(sys.argv):
            output_dir = Path(sys.argv[i + 1])
            i += 2
        else:
            evidence_dirs.append(Path(sys.argv[i]))
            i += 1

    if output_dir:
        output_dir = Path(output_dir)

    analyze(evidence_dirs, output_dir)
