#!/usr/bin/env python3
"""
Structure Quality Metrics for Learning Mode Evaluation

Measures planning intelligence: Does the Planner derive good structure from memory?
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional


def load_capture(run_dir: Path) -> Optional[dict]:
    """Load capture.json from run directory."""
    capture_path = run_dir / "capture.json"
    if not capture_path.exists():
        return None
    with open(capture_path) as f:
        return json.load(f)


def load_memory(memory_dir: Path) -> dict:
    """Load all memory files."""
    memory = {
        "patterns": [],
        "failure_modes": [],
        "learnings": []
    }

    # Load patterns from JSON files
    patterns_dir = memory_dir / "patterns"
    if patterns_dir.exists():
        for json_file in patterns_dir.glob("*.json"):
            with open(json_file) as f:
                data = json.load(f)
                if "meta_patterns" in data:
                    memory["patterns"].extend(data["meta_patterns"])
                if "failure_modes" in data:
                    memory["failure_modes"].extend(data["failure_modes"])

    # Load learnings from chronicle.md
    chronicle_path = memory_dir.parent / "chronicle.md"
    if chronicle_path.exists():
        content = chronicle_path.read_text()
        # Extract L### patterns
        learning_pattern = r'\*\*(L\d+)\*\*:?\s*(.+?)(?=\n\n|\n\*\*L\d+|$)'
        matches = re.findall(learning_pattern, content, re.DOTALL)
        for lid, insight in matches:
            memory["learnings"].append({"id": lid, "insight": insight.strip()})

    return memory


def extract_planner_reasoning(capture: dict) -> dict:
    """Extract planner's memory reasoning from capture."""
    reasoning = {
        "patterns_referenced": [],
        "failures_referenced": [],
        "learnings_referenced": [],
        "task_types": [],
        "has_spec_phase": False
    }

    # Find planner agent
    for agent in capture.get("agents", []):
        if agent.get("type") == "planner":
            content = agent.get("first_message", "").lower()

            # Check for pattern references
            pattern_refs = re.findall(r'pattern[:\s]+([a-z-]+)', content)
            reasoning["patterns_referenced"] = list(set(pattern_refs))

            # Check for failure mode references
            failure_refs = re.findall(r'failure[:\s]+([a-z-]+)', content)
            reasoning["failures_referenced"] = list(set(failure_refs))

            # Check for learning references
            learning_refs = re.findall(r'(L\d+)', content)
            reasoning["learnings_referenced"] = list(set(learning_refs))

            # Check for task types
            if "spec" in content or "test-spec" in content:
                reasoning["has_spec_phase"] = True

            # Extract task types from table
            type_refs = re.findall(r'\|\s*(SPEC|BUILD|VERIFY)\s*\|', content, re.IGNORECASE)
            reasoning["task_types"] = [t.upper() for t in type_refs]

            break

    return reasoning


def calculate_metrics(capture: dict, memory: dict) -> dict:
    """Calculate structure quality metrics."""
    reasoning = extract_planner_reasoning(capture)

    # Count totals
    total_patterns = len(memory.get("patterns", []))
    total_failures = len(memory.get("failure_modes", []))
    total_learnings = len(memory.get("learnings", []))

    patterns_applied = len(reasoning["patterns_referenced"])
    failures_avoided = len(reasoning["failures_referenced"])
    learnings_applied = len(reasoning["learnings_referenced"])

    # Calculate rates
    pattern_application_rate = patterns_applied / max(total_patterns, 1)
    failure_avoidance_rate = failures_avoided / max(total_failures, 1)
    learning_application_rate = learnings_applied / max(total_learnings, 1)

    # Task structure analysis
    task_types = reasoning["task_types"]
    total_tasks = len(task_types)

    has_spec_phase = reasoning["has_spec_phase"] or "SPEC" in task_types
    has_verify_phase = "VERIFY" in task_types
    build_count = task_types.count("BUILD")

    # Memory derivation: tasks derived from memory vs total
    memory_derived = patterns_applied + failures_avoided + learnings_applied
    memory_derivation_ratio = memory_derived / max(total_tasks, 1)

    # Calculate planner overhead from capture
    planner_tokens = 0
    total_tokens = 0
    for agent in capture.get("agents", []):
        tokens = agent.get("tokens", 0)
        total_tokens += tokens
        if agent.get("type") == "planner":
            planner_tokens = tokens

    planning_overhead = planner_tokens / max(total_tokens, 1)

    return {
        "pattern_application_rate": round(pattern_application_rate, 3),
        "failure_avoidance_rate": round(failure_avoidance_rate, 3),
        "learning_application_rate": round(learning_application_rate, 3),
        "memory_derivation_ratio": round(memory_derivation_ratio, 3),
        "planning_overhead": round(planning_overhead, 3),
        "structure": {
            "has_spec_phase": has_spec_phase,
            "has_verify_phase": has_verify_phase,
            "build_count": build_count,
            "total_tasks": total_tasks,
            "task_types": task_types
        },
        "memory_references": {
            "patterns": reasoning["patterns_referenced"],
            "failures": reasoning["failures_referenced"],
            "learnings": reasoning["learnings_referenced"]
        },
        "memory_available": {
            "patterns": total_patterns,
            "failure_modes": total_failures,
            "learnings": total_learnings
        }
    }


def assess_quality(metrics: dict) -> dict:
    """Assess overall structure quality against targets."""
    targets = {
        "pattern_application_rate": 0.8,
        "failure_avoidance_rate": 1.0,
        "planning_overhead": 0.1,
        "memory_derivation_ratio": 0.6
    }

    assessment = {}
    for metric, target in targets.items():
        actual = metrics.get(metric, 0)
        if metric == "planning_overhead":
            # Lower is better
            passed = actual <= target
        else:
            # Higher is better
            passed = actual >= target

        assessment[metric] = {
            "actual": actual,
            "target": target,
            "passed": passed
        }

    # Special checks
    assessment["has_spec_phase"] = {
        "actual": metrics["structure"]["has_spec_phase"],
        "target": True,
        "passed": metrics["structure"]["has_spec_phase"]
    }

    # Overall
    passed_count = sum(1 for a in assessment.values() if a["passed"])
    total_count = len(assessment)

    return {
        "checks": assessment,
        "passed": passed_count,
        "total": total_count,
        "score": round(passed_count / total_count, 2)
    }


def compare_runs(run_dirs: list[Path], memory_dir: Path) -> dict:
    """Compare structure evolution across multiple runs."""
    evolution = []

    for run_dir in sorted(run_dirs):
        capture = load_capture(run_dir)
        if not capture:
            continue

        memory = load_memory(memory_dir)
        metrics = calculate_metrics(capture, memory)
        assessment = assess_quality(metrics)

        evolution.append({
            "run": run_dir.name,
            "metrics": metrics,
            "assessment": assessment
        })

    # Calculate deltas
    if len(evolution) >= 2:
        for i in range(1, len(evolution)):
            prev = evolution[i - 1]["metrics"]
            curr = evolution[i]["metrics"]

            evolution[i]["delta"] = {
                "pattern_application_rate": round(
                    curr["pattern_application_rate"] - prev["pattern_application_rate"], 3
                ),
                "failure_avoidance_rate": round(
                    curr["failure_avoidance_rate"] - prev["failure_avoidance_rate"], 3
                ),
                "task_count_change": (
                    curr["structure"]["total_tasks"] - prev["structure"]["total_tasks"]
                )
            }

    return {
        "runs": evolution,
        "trajectory": "improving" if len(evolution) >= 2 and
                      evolution[-1]["assessment"]["score"] > evolution[0]["assessment"]["score"]
                      else "stable" if len(evolution) >= 2 and
                      evolution[-1]["assessment"]["score"] == evolution[0]["assessment"]["score"]
                      else "needs_work"
    }


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: structure_quality.py <run_dir> [memory_dir]")
        print("       structure_quality.py compare <run_dir1> <run_dir2> ... [--memory memory_dir]")
        sys.exit(1)

    if sys.argv[1] == "compare":
        # Compare mode
        run_dirs = []
        memory_dir = None

        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "--memory":
                memory_dir = Path(sys.argv[i + 1])
                i += 2
            else:
                run_dirs.append(Path(sys.argv[i]))
                i += 1

        if not memory_dir:
            memory_dir = Path(".ftl/memory")

        result = compare_runs(run_dirs, memory_dir)
        print(json.dumps(result, indent=2))
    else:
        # Single run mode
        run_dir = Path(sys.argv[1])
        memory_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".ftl/memory")

        capture = load_capture(run_dir)
        if not capture:
            print(f"Error: No capture.json found in {run_dir}")
            sys.exit(1)

        memory = load_memory(memory_dir)
        metrics = calculate_metrics(capture, memory)
        assessment = assess_quality(metrics)

        result = {
            "run": run_dir.name,
            "computed_at": datetime.now().isoformat(),
            "metrics": metrics,
            "assessment": assessment
        }

        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
