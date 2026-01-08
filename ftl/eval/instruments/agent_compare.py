#!/usr/bin/env python3
"""Compare matched agent pairs across FTL evaluation runs.

Matches agents by (spawn_order, type, task_id) and computes per-agent
epiplexity metrics to generate actionable recommendations.

Usage:
    python3 agent_compare.py evidence/runs/anki-v13 evidence/runs/anki-v17
    python3 agent_compare.py evidence/runs/anki-v13 evidence/runs/anki-v17 --output recommendations/

Produces:
    - agent_comparison.json: Structured comparison data
    - recommendations.md: Actionable agent changes with evidence
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from statistics import mean


def load_metrics(evidence_dir: Path) -> dict:
    """Load metrics.json from evidence directory."""
    metrics_path = evidence_dir / "metrics.json"
    if not metrics_path.exists():
        print(f"Error: {metrics_path} not found")
        sys.exit(1)
    with open(metrics_path) as f:
        return json.load(f)


def compute_agent_epiplexity(agent: dict) -> dict:
    """Compute epiplexity metrics for single agent."""
    seq = agent.get("tool_sequence", [])
    reasoning = agent.get("reasoning_trace", [])
    tools = agent.get("tools", {})

    # Action tools that produce output
    action_tools = {"Write", "Edit", "Bash"}

    # First action position: how many tools before first Write/Edit/Bash
    first_action = next((i for i, t in enumerate(seq) if t in action_tools), len(seq))
    exploration_overhead = first_action / max(len(seq), 1)

    # Action density: what fraction of tool calls are actions
    action_count = sum(1 for t in seq if t in action_tools)
    action_density = action_count / max(len(seq), 1)

    # Reasoning efficiency: reasoning steps per 1K output tokens
    output_tokens = agent["tokens"]["output"]
    reasoning_efficiency = len(reasoning) / max(output_tokens / 1000, 1)

    # Exploration tools used
    glob_used = tools.get("Glob", 0) > 0
    grep_used = tools.get("Grep", 0) > 0
    read_count = tools.get("Read", 0)

    return {
        "exploration_overhead": round(exploration_overhead, 3),
        "action_density": round(action_density, 3),
        "reasoning_efficiency": round(reasoning_efficiency, 3),
        "first_action_position": first_action,
        "total_tools": len(seq),
        "reasoning_depth": len(reasoning),
        "glob_used": glob_used,
        "grep_used": grep_used,
        "read_count": read_count,
    }


def detect_behavioral_changes(a: dict, b: dict, epi_a: dict, epi_b: dict) -> list:
    """Detect specific behavioral changes between two agents."""
    changes = []

    # Glob removal
    if epi_a["glob_used"] and not epi_b["glob_used"]:
        changes.append("Removed Glob exploration")
    elif not epi_a["glob_used"] and epi_b["glob_used"]:
        changes.append("Added Glob exploration")

    # Read reduction
    read_delta = epi_b["read_count"] - epi_a["read_count"]
    if read_delta <= -3:
        changes.append(f"Fewer Reads ({epi_a['read_count']} → {epi_b['read_count']})")
    elif read_delta >= 3:
        changes.append(f"More Reads ({epi_a['read_count']} → {epi_b['read_count']})")

    # Earlier action
    if epi_b["first_action_position"] < epi_a["first_action_position"] - 1:
        changes.append(f"Earlier first action (pos {epi_a['first_action_position']} → {epi_b['first_action_position']})")
    elif epi_b["first_action_position"] > epi_a["first_action_position"] + 1:
        changes.append(f"Later first action (pos {epi_a['first_action_position']} → {epi_b['first_action_position']})")

    # Reasoning depth
    reason_delta = epi_b["reasoning_depth"] - epi_a["reasoning_depth"]
    if reason_delta <= -3:
        changes.append(f"Shallower reasoning ({epi_a['reasoning_depth']} → {epi_b['reasoning_depth']})")
    elif reason_delta >= 3:
        changes.append(f"Deeper reasoning ({epi_a['reasoning_depth']} → {epi_b['reasoning_depth']})")

    # Tool count
    tool_delta = epi_b["total_tools"] - epi_a["total_tools"]
    if tool_delta <= -5:
        changes.append(f"Fewer tool calls ({epi_a['total_tools']} → {epi_b['total_tools']})")
    elif tool_delta >= 5:
        changes.append(f"More tool calls ({epi_a['total_tools']} → {epi_b['total_tools']})")

    # Action density shift
    density_delta = epi_b["action_density"] - epi_a["action_density"]
    if density_delta >= 0.15:
        changes.append(f"Higher action density ({epi_a['action_density']:.0%} → {epi_b['action_density']:.0%})")
    elif density_delta <= -0.15:
        changes.append(f"Lower action density ({epi_a['action_density']:.0%} → {epi_b['action_density']:.0%})")

    return changes


def compare_agent_pair(a: dict, b: dict) -> dict:
    """Compare a matched pair of agents."""
    epi_a = compute_agent_epiplexity(a)
    epi_b = compute_agent_epiplexity(b)

    tokens_a = a["tokens"]["total"]
    tokens_b = b["tokens"]["total"]
    token_delta = (tokens_b - tokens_a) / tokens_a if tokens_a > 0 else 0

    changes = detect_behavioral_changes(a, b, epi_a, epi_b)

    return {
        "step": a.get("spawn_order"),
        "type": a["type"],
        "task": a.get("task_id"),
        "a": {
            "file": a["file"][:13],
            "tokens": tokens_a,
            "tools": epi_a["total_tools"],
            "reasoning": epi_a["reasoning_depth"],
            "epiplexity": epi_a,
        },
        "b": {
            "file": b["file"][:13],
            "tokens": tokens_b,
            "tools": epi_b["total_tools"],
            "reasoning": epi_b["reasoning_depth"],
            "epiplexity": epi_b,
        },
        "delta": {
            "tokens": round(token_delta, 3),
            "tokens_abs": tokens_b - tokens_a,
            "tools": epi_b["total_tools"] - epi_a["total_tools"],
            "reasoning": epi_b["reasoning_depth"] - epi_a["reasoning_depth"],
        },
        "behavioral_changes": changes,
    }


def generate_recommendation(agent_type: str, pairs: list) -> dict | None:
    """Generate recommendation for an agent type based on pair comparisons."""
    if not pairs:
        return None

    # Compute average token delta
    deltas = [p["delta"]["tokens"] for p in pairs]
    avg_delta = mean(deltas)

    # Check consistency (all same direction)
    all_improved = all(d < -0.1 for d in deltas)
    all_regressed = all(d > 0.1 for d in deltas)
    consistent = all_improved or all_regressed or all(abs(d) <= 0.1 for d in deltas)

    # Collect all behavioral changes
    all_changes = []
    for p in pairs:
        all_changes.extend(p["behavioral_changes"])

    # Count change frequencies
    change_counts = defaultdict(int)
    for c in all_changes:
        # Normalize similar changes
        key = c.split("(")[0].strip()
        change_counts[key] += 1

    # Most common changes
    common_changes = sorted(change_counts.items(), key=lambda x: -x[1])

    # Generate recommendation
    if avg_delta < -0.2 and common_changes:
        primary_change = common_changes[0][0]
        evidence_pairs = [p for p in pairs if any(primary_change in c for c in p["behavioral_changes"])]

        return {
            "agent": f"{agent_type}.md",
            "avg_delta": round(avg_delta, 3),
            "consistent": consistent,
            "primary_change": primary_change,
            "change_frequency": dict(common_changes[:3]),
            "evidence_count": len(evidence_pairs),
            "sample_evidence": f"{pairs[0]['a']['tokens']:,} → {pairs[0]['b']['tokens']:,} tokens",
        }
    elif avg_delta > 0.1:
        return {
            "agent": f"{agent_type}.md",
            "avg_delta": round(avg_delta, 3),
            "consistent": consistent,
            "primary_change": "No improvement (regression or stable)",
            "recommendation": "Review for potential issues" if avg_delta > 0.3 else "No changes needed",
        }

    return None


def compare_runs(evidence_a: Path, evidence_b: Path) -> dict:
    """Main comparison function."""
    metrics_a = load_metrics(evidence_a)
    metrics_b = load_metrics(evidence_b)

    agents_a = sorted(metrics_a["agents"], key=lambda x: x.get("spawn_order", 99))
    agents_b = sorted(metrics_b["agents"], key=lambda x: x.get("spawn_order", 99))

    # Match agents by spawn_order
    pairs = []
    for a, b in zip(agents_a, agents_b):
        if a["type"] != b["type"]:
            print(f"Warning: Type mismatch at step {a.get('spawn_order')}: {a['type']} vs {b['type']}")
            continue
        pairs.append(compare_agent_pair(a, b))

    # Group by type
    by_type = defaultdict(list)
    for p in pairs:
        by_type[p["type"]].append(p)

    # Compute type-level summaries
    type_summaries = {}
    for agent_type, type_pairs in by_type.items():
        deltas = [p["delta"]["tokens"] for p in type_pairs]
        type_summaries[agent_type] = {
            "count": len(type_pairs),
            "avg_token_delta": round(mean(deltas), 3) if deltas else 0,
            "total_tokens_saved": sum(p["delta"]["tokens_abs"] for p in type_pairs),
        }

    # Generate recommendations
    recommendations = []
    for agent_type, type_pairs in by_type.items():
        rec = generate_recommendation(agent_type, type_pairs)
        if rec:
            recommendations.append(rec)

    return {
        "comparison": {
            "run_a": metrics_a["run_id"],
            "run_b": metrics_b["run_id"],
            "computed_at": datetime.now().isoformat(),
        },
        "pairs": pairs,
        "by_type": type_summaries,
        "recommendations": recommendations,
    }


def generate_recommendations_md(result: dict) -> str:
    """Generate markdown recommendations report."""
    lines = [
        f"# FTL Agent Recommendations: {result['comparison']['run_a']} → {result['comparison']['run_b']}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
        "## Summary by Agent Type",
        "",
        "| Type | Count | Avg Token Delta | Total Saved |",
        "|------|-------|-----------------|-------------|",
    ]

    for agent_type in ["planner", "router", "builder", "synthesizer"]:
        if agent_type in result["by_type"]:
            data = result["by_type"][agent_type]
            delta_pct = f"{data['avg_token_delta']:+.0%}"
            saved = f"{data['total_tokens_saved']:+,}"
            lines.append(f"| {agent_type} | {data['count']} | {delta_pct} | {saved} |")

    lines.extend(["", "---", "", "## Recommendations", ""])

    if not result["recommendations"]:
        lines.append("*No significant improvements detected requiring protocol changes.*")
    else:
        for rec in sorted(result["recommendations"], key=lambda x: x["avg_delta"]):
            lines.append(f"### {rec['agent']}")
            lines.append("")
            lines.append(f"**Average Delta**: {rec['avg_delta']:+.0%}")
            lines.append(f"**Consistent**: {'Yes' if rec.get('consistent') else 'No'}")
            lines.append(f"**Primary Change**: {rec.get('primary_change', 'N/A')}")
            lines.append("")

            if "change_frequency" in rec:
                lines.append("**Observed Changes**:")
                for change, count in rec["change_frequency"].items():
                    lines.append(f"  - {change} ({count}x)")
                lines.append("")

            if "sample_evidence" in rec:
                lines.append(f"**Sample Evidence**: {rec['sample_evidence']}")
                lines.append("")

            lines.append("---")
            lines.append("")

    # Detailed pair analysis
    lines.extend(["## Agent Pair Details", ""])

    for pair in result["pairs"]:
        task_str = f"task {pair['task']}" if pair["task"] else ""
        header = f"### Step {pair['step']}: {pair['type']} {task_str}".strip()
        lines.append(header)
        lines.append("")

        delta_pct = f"{pair['delta']['tokens']:+.0%}"
        lines.append(f"**Tokens**: {pair['a']['tokens']:,} → {pair['b']['tokens']:,} ({delta_pct})")
        lines.append(f"**Tools**: {pair['a']['tools']} → {pair['b']['tools']}")
        lines.append(f"**Reasoning Depth**: {pair['a']['reasoning']} → {pair['b']['reasoning']}")
        lines.append("")

        if pair["behavioral_changes"]:
            lines.append("**Behavioral Changes**:")
            for change in pair["behavioral_changes"]:
                lines.append(f"  - {change}")
            lines.append("")

        # Epiplexity metrics
        epi_a = pair["a"]["epiplexity"]
        epi_b = pair["b"]["epiplexity"]
        lines.append("**Epiplexity Metrics**:")
        lines.append(f"  - Exploration overhead: {epi_a['exploration_overhead']:.0%} → {epi_b['exploration_overhead']:.0%}")
        lines.append(f"  - Action density: {epi_a['action_density']:.0%} → {epi_b['action_density']:.0%}")
        lines.append(f"  - First action pos: {epi_a['first_action_position']} → {epi_b['first_action_position']}")
        lines.append("")

    return "\n".join(lines)


def compare(evidence_a: Path, evidence_b: Path, output_dir: Path = None):
    """Main entry point."""
    result = compare_runs(evidence_a, evidence_b)

    # Default output location
    if output_dir is None:
        output_dir = evidence_b.parent

    output_dir.mkdir(parents=True, exist_ok=True)

    # Write JSON
    json_path = output_dir / "agent_comparison.json"
    with open(json_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote: {json_path}")

    # Write markdown
    md_path = output_dir / "recommendations.md"
    with open(md_path, "w") as f:
        f.write(generate_recommendations_md(result))
    print(f"Wrote: {md_path}")

    # Print summary
    print(f"\n{result['comparison']['run_a']} → {result['comparison']['run_b']}")
    print(f"Matched pairs: {len(result['pairs'])}")

    for agent_type, data in result["by_type"].items():
        print(f"  {agent_type}: {data['avg_token_delta']:+.0%} ({data['total_tokens_saved']:+,} tokens)")

    if result["recommendations"]:
        print("\nRecommendations:")
        for rec in result["recommendations"]:
            print(f"  - {rec['agent']}: {rec.get('primary_change', 'Review needed')}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 agent_compare.py <evidence_a> <evidence_b> [--output <dir>]")
        sys.exit(1)

    evidence_a = Path(sys.argv[1])
    evidence_b = Path(sys.argv[2])

    output_dir = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_dir = Path(sys.argv[idx + 1])

    compare(evidence_a, evidence_b, output_dir)
