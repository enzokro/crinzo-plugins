#!/usr/bin/env python3
"""Compute information theory metrics from FTL evaluation runs.

Based on the epiplexity paper concepts:
- Epiplexity (ST): Structural information extractable by bounded observer
- Time-Bounded Entropy (HT): Random, unpredictable components
- Prequential coding: Area under loss curve above final baseline

Usage:
    python3 info_theory.py evidence/runs/anki-v15
    python3 info_theory.py evidence/runs/anki-v15 --verbose

Produces:
    - info_theory.json: Information theory metrics
"""

import json
import sys
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from statistics import mean, stdev, variance
import re


# Canonical tool sequences by agent type (expected "optimal" behavior)
CANONICAL_SEQUENCES = {
    "router": ["Read", "Read", "Bash", "Write"],  # Context → explore → workspace
    "builder": ["Read", "Read", "Edit", "Bash"],  # Spec → code → edit → verify
    "planner": ["Read", "Read", "Read"],  # Explore project structure
    "synthesizer": ["Read", "Read", "Bash"],  # Read workspaces → write synthesis
    "learner": ["Read", "Read", "Edit"],  # Read → extract → write pattern
    "reflector": ["Read"],  # Read verification output
}

# Weights for epiplexity components
WEIGHTS = {
    "canonical_sequence": 2.0,  # Following expected tool order
    "type_consistency": 1.5,    # Agent type matches behavior
    "single_attempt": 3.0,      # Task completed without retry
    "cache_efficiency": 1.0,    # Context reuse
}

# Penalties for entropy components
PENALTIES = {
    "retry": 5.0,        # Each retry attempt
    "fallback": 3.0,     # Each fallback usage
    "variance": 1.0,     # Normalized variance contribution
}

# Cognitive trace patterns for semantic analysis
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


def compute_agent_cognition(agent: dict) -> dict:
    """Compute cognitive metrics from reasoning traces."""
    traces = agent.get("reasoning_trace", [])

    if not traces:
        return {
            "trace_count": 0,
            "explore_count": 0,
            "action_count": 0,
            "action_explore_ratio": None,
            "first_action_position": -1,
            "trace_pattern": "",
        }

    classifications = [classify_thinking(t.get("thinking", "")) for t in traces]

    explore_count = classifications.count("explore")
    action_count = classifications.count("action")

    # Action/explore ratio
    if explore_count > 0:
        ratio = action_count / explore_count
    elif action_count > 0:
        ratio = 999.0  # All action, no explore
    else:
        ratio = None  # All neutral

    # First action position
    first_action = -1
    for i, c in enumerate(classifications):
        if c == "action":
            first_action = i
            break

    # Pattern string (E=explore, A=action, .=neutral)
    pattern = "".join(
        "E" if c == "explore" else "A" if c == "action" else "."
        for c in classifications
    )

    return {
        "trace_count": len(traces),
        "explore_count": explore_count,
        "action_count": action_count,
        "action_explore_ratio": round(ratio, 2) if ratio is not None and ratio < 100 else ratio,
        "first_action_position": first_action,
        "trace_pattern": pattern,
    }


def load_metrics(evidence_dir: Path) -> dict:
    """Load metrics.json from evidence directory."""
    metrics_path = evidence_dir / "metrics.json"
    if not metrics_path.exists():
        print(f"Error: {metrics_path} not found")
        sys.exit(1)
    with open(metrics_path) as f:
        return json.load(f)


def compute_agent_epiplexity(agent: dict) -> dict:
    """Compute per-agent epiplexity metrics.

    Measures structural information extractable from agent behavior:
    - exploration_overhead: fraction of tools before first action
    - action_density: fraction of tools that produce output
    - reasoning_efficiency: reasoning steps per 1K output tokens
    """
    seq = agent.get("tool_sequence", [])
    reasoning = agent.get("reasoning_trace", [])
    tools = agent.get("tools", {})

    # Action tools that produce output
    action_tools = {"Write", "Edit", "Bash"}

    # First action position
    first_action = next((i for i, t in enumerate(seq) if t in action_tools), len(seq))
    exploration_overhead = first_action / max(len(seq), 1)

    # Action density
    action_count = sum(1 for t in seq if t in action_tools)
    action_density = action_count / max(len(seq), 1)

    # Reasoning efficiency
    output_tokens = agent["tokens"]["output"]
    reasoning_efficiency = len(reasoning) / max(output_tokens / 1000, 1)

    return {
        "exploration_overhead": round(exploration_overhead, 3),
        "action_density": round(action_density, 3),
        "reasoning_efficiency": round(reasoning_efficiency, 3),
        "first_action_position": first_action,
        "total_tools": len(seq),
        "reasoning_depth": len(reasoning),
        "glob_used": tools.get("Glob", 0) > 0,
        "read_count": tools.get("Read", 0),
    }


def levenshtein_distance(seq1: list, seq2: list) -> int:
    """Compute edit distance between two sequences."""
    if len(seq1) < len(seq2):
        return levenshtein_distance(seq2, seq1)
    if len(seq2) == 0:
        return len(seq1)

    prev_row = range(len(seq2) + 1)
    for i, c1 in enumerate(seq1):
        curr_row = [i + 1]
        for j, c2 in enumerate(seq2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row

    return prev_row[-1]


def sequence_similarity(actual: list, canonical: list) -> float:
    """Compute similarity between actual and canonical sequence (0-1)."""
    if not canonical:
        return 0.5  # No canonical = neutral
    if not actual:
        return 0.0

    # Truncate to canonical length for comparison
    actual_prefix = actual[:len(canonical)]
    distance = levenshtein_distance(actual_prefix, canonical)
    max_len = max(len(actual_prefix), len(canonical))
    return 1.0 - (distance / max_len) if max_len > 0 else 1.0


def compute_epiplexity(metrics: dict, verbose: bool = False) -> dict:
    """Compute epiplexity (structural information) from metrics."""
    agents = metrics.get("agents", [])
    if not agents:
        return {"total": 0, "components": {}, "by_type": {}}

    # Component accumulators
    canonical_score = 0.0
    type_consistency_score = 0.0
    single_attempt_score = 0.0
    cache_efficiency_score = 0.0

    by_type = defaultdict(float)

    # Analyze each agent
    for agent in agents:
        atype = agent.get("type", "unknown")
        tool_seq = agent.get("tool_sequence", [])
        canonical = CANONICAL_SEQUENCES.get(atype, [])

        # Canonical sequence adherence
        sim = sequence_similarity(tool_seq, canonical)
        agent_canonical = sim * WEIGHTS["canonical_sequence"]
        canonical_score += agent_canonical

        # Type consistency (does behavior match type expectations?)
        # High similarity = high consistency
        type_score = sim * WEIGHTS["type_consistency"]
        type_consistency_score += type_score

        # Accumulate by type
        by_type[atype] += agent_canonical + type_score

        if verbose:
            print(f"  {agent['file'][:13]} ({atype}): seq_sim={sim:.2f}")

    # Single-attempt completions (from task_flow)
    task_flow = metrics.get("task_flow", {})
    for task_id, flow in task_flow.items():
        if flow.get("attempts", 1) == 1:
            single_attempt_score += WEIGHTS["single_attempt"]
            # Attribute to builder type (completes tasks)
            by_type["builder"] += WEIGHTS["single_attempt"] / max(len(task_flow), 1)

    # Cache efficiency contribution
    cache_eff = metrics.get("cache_efficiency", 0)
    cache_efficiency_score = cache_eff * WEIGHTS["cache_efficiency"] * len(agents)

    # Distribute cache score across router type (they use cache most)
    router_count = metrics.get("by_type", {}).get("router", {}).get("count", 1)
    by_type["router"] += cache_efficiency_score / max(router_count, 1)

    total = canonical_score + type_consistency_score + single_attempt_score + cache_efficiency_score

    return {
        "total": round(total, 2),
        "components": {
            "canonical_sequences": round(canonical_score, 2),
            "type_consistency": round(type_consistency_score, 2),
            "single_attempts": round(single_attempt_score, 2),
            "cache_efficiency": round(cache_efficiency_score, 2),
        },
        "by_type": {k: round(v, 2) for k, v in by_type.items()},
    }


def compute_entropy(metrics: dict, verbose: bool = False) -> dict:
    """Compute time-bounded entropy (unpredictable components) from metrics."""
    agents = metrics.get("agents", [])
    loop_signals = metrics.get("loop_signals", {})

    # Retry penalty
    tasks_failed = loop_signals.get("tasks_failed", 0)
    retry_penalty = tasks_failed * PENALTIES["retry"]

    # Fallback penalty
    fallback_count = loop_signals.get("fallback_used", 0)
    fallback_penalty = fallback_count * PENALTIES["fallback"]

    # Variance penalty (reasoning trace length variance)
    reasoning_depths = []
    for agent in agents:
        trace = agent.get("reasoning_trace", [])
        reasoning_depths.append(len(trace))

    variance_penalty = 0.0
    if len(reasoning_depths) > 1 and mean(reasoning_depths) > 0:
        # Coefficient of variation as normalized variance measure
        cv = stdev(reasoning_depths) / mean(reasoning_depths)
        variance_penalty = cv * PENALTIES["variance"] * len(agents)

    if verbose:
        print(f"  Retries: {tasks_failed} (penalty: {retry_penalty})")
        print(f"  Fallbacks: {fallback_count} (penalty: {fallback_penalty})")
        print(f"  Reasoning depths: {reasoning_depths}")
        print(f"  Variance penalty: {variance_penalty:.2f}")

    total = retry_penalty + fallback_penalty + variance_penalty

    return {
        "total": round(total, 2),
        "components": {
            "retries": round(retry_penalty, 2),
            "fallbacks": round(fallback_penalty, 2),
            "variance": round(variance_penalty, 2),
        },
    }


def compute_loss_curve(metrics: dict, verbose: bool = False) -> dict:
    """Compute prequential loss curve approximation.

    Uses token consumption as proxy for "loss" - early agents typically
    consume more tokens exploring, later agents converge to efficient patterns.
    """
    agents = metrics.get("agents", [])
    if not agents:
        return {"area": 0, "baseline": 0, "trajectory": []}

    # Sort by spawn order
    sorted_agents = sorted(
        [a for a in agents if a.get("spawn_order") is not None],
        key=lambda a: a["spawn_order"]
    )

    if not sorted_agents:
        sorted_agents = agents

    # Extract token trajectory
    token_trajectory = [a["tokens"]["total"] for a in sorted_agents]

    if not token_trajectory:
        return {"area": 0, "baseline": 0, "trajectory": []}

    # Baseline = mean of last 3 agents (or all if fewer)
    baseline_agents = token_trajectory[-3:] if len(token_trajectory) >= 3 else token_trajectory
    baseline = mean(baseline_agents)

    if baseline == 0:
        baseline = 1  # Avoid division by zero

    # Compute normalized trajectory and area above baseline
    normalized = [t / baseline for t in token_trajectory]
    area = sum(max(0, n - 1.0) for n in normalized)

    # Compute slope (negative = improving, positive = degrading)
    if len(normalized) > 1:
        # Simple linear regression slope
        n = len(normalized)
        x_mean = (n - 1) / 2
        y_mean = mean(normalized)
        numerator = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(normalized))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / denominator if denominator != 0 else 0
    else:
        slope = 0

    if verbose:
        print(f"  Token trajectory: {token_trajectory}")
        print(f"  Normalized: {[round(n, 2) for n in normalized]}")
        print(f"  Baseline: {baseline:.0f}")
        print(f"  Area above baseline: {area:.2f}")
        print(f"  Slope: {slope:.4f}")

    return {
        "area": round(area, 2),
        "baseline": round(baseline, 0),
        "slope": round(slope, 4),
        "trajectory": [round(n, 3) for n in normalized],
    }


def generate_observations(epiplexity: dict, entropy: dict, loss_curve: dict, metrics: dict) -> list:
    """Generate human-readable observations from computed metrics."""
    observations = []

    # Epiplexity observations
    st = epiplexity["total"]
    if st > 40:
        observations.append("High structural information - execution follows learnable patterns")
    elif st < 20:
        observations.append("Low structural information - execution is less predictable")

    # Single attempt observation
    single_attempts = epiplexity["components"]["single_attempts"]
    task_count = len(metrics.get("task_flow", {}))
    if task_count > 0:
        attempt_rate = single_attempts / (task_count * WEIGHTS["single_attempt"])
        if attempt_rate >= 0.9:
            observations.append(f"All {task_count} tasks completed single-attempt (strong task definitions)")
        elif attempt_rate < 0.5:
            observations.append(f"Multiple retries detected (task definitions may need refinement)")

    # Entropy observations
    ht = entropy["total"]
    if entropy["components"]["retries"] > 0:
        observations.append(f"Retries present ({entropy['components']['retries']:.0f} penalty) - indicates task failures")
    if entropy["components"]["fallbacks"] > 0:
        observations.append(f"Fallbacks used ({entropy['components']['fallbacks']:.0f} penalty) - environmental issues")
    if entropy["components"]["variance"] > 10:
        observations.append("High reasoning variance - agent execution varies significantly")

    # Loss curve observations
    if loss_curve["slope"] < -0.1:
        observations.append("Improving trajectory - later agents more efficient than early ones")
    elif loss_curve["slope"] > 0.1:
        observations.append("Degrading trajectory - token consumption increased over time")

    # Cache observation
    cache_eff = metrics.get("cache_efficiency", 0)
    if cache_eff > 0.8:
        observations.append(f"Cache efficiency {cache_eff:.1%} indicates strong context reuse")
    elif cache_eff < 0.5:
        observations.append(f"Low cache efficiency {cache_eff:.1%} - context not being reused effectively")

    return observations


def compute_info_theory(evidence_dir: Path, verbose: bool = False) -> dict:
    """Main computation function."""
    metrics = load_metrics(evidence_dir)

    if verbose:
        print(f"\n=== Epiplexity Computation ===")
    epiplexity = compute_epiplexity(metrics, verbose)

    if verbose:
        print(f"\n=== Entropy Computation ===")
    entropy = compute_entropy(metrics, verbose)

    if verbose:
        print(f"\n=== Loss Curve Computation ===")
    loss_curve = compute_loss_curve(metrics, verbose)

    # Info Gain Ratio
    st = epiplexity["total"]
    ht = entropy["total"]
    igr = st / (st + ht) if (st + ht) > 0 else 0.5

    # Generate observations
    observations = generate_observations(epiplexity, entropy, loss_curve, metrics)

    # Compute per-agent epiplexity and cognitive metrics
    agents = metrics.get("agents", [])
    per_agent = []
    for agent in sorted(agents, key=lambda a: a.get("spawn_order", 99)):
        agent_epi = compute_agent_epiplexity(agent)
        agent_cog = compute_agent_cognition(agent)
        per_agent.append({
            "step": agent.get("spawn_order"),
            "type": agent["type"],
            "task": agent.get("task_id"),
            "tokens": agent["tokens"]["total"],
            "epiplexity": agent_epi,
            "cognition": agent_cog,
        })

    result = {
        "run_id": metrics.get("run_id", evidence_dir.name),
        "computed_at": datetime.now().isoformat(),
        "observer": "haiku-bounded",

        "epiplexity": epiplexity,
        "entropy": entropy,
        "info_gain_ratio": round(igr, 3),
        "loss_curve": loss_curve,

        "observations": observations,

        # Per-agent granular metrics
        "per_agent": per_agent,

        # Summary for quick reference
        "summary": {
            "ST": round(st, 1),
            "HT": round(ht, 1),
            "IGR": round(igr, 2),
            "interpretation": (
                "highly structured" if igr > 0.8 else
                "mixed structure/noise" if igr > 0.5 else
                "high entropy"
            ),
        },
    }

    return result


def analyze(evidence_dir: Path, output_path: Path = None, verbose: bool = False):
    """Main analysis function."""
    if not evidence_dir.exists():
        print(f"Error: {evidence_dir} does not exist")
        sys.exit(1)

    result = compute_info_theory(evidence_dir, verbose)

    # Default output location
    if output_path is None:
        output_path = evidence_dir / "info_theory.json"

    # Write output
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"Wrote: {output_path}")

    # Print summary
    summary = result["summary"]
    print(f"\n{result['run_id']}: ST={summary['ST']}, HT={summary['HT']}, IGR={summary['IGR']} ({summary['interpretation']})")

    if result["observations"]:
        print("\nObservations:")
        for obs in result["observations"]:
            print(f"  - {obs}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 info_theory.py <evidence_dir> [--verbose] [--output <path>]")
        sys.exit(1)

    evidence_dir = Path(sys.argv[1])
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[idx + 1])

    analyze(evidence_dir, output_path, verbose)
