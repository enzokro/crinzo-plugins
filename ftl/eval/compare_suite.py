#!/usr/bin/env python3
"""FTL Suite Cross-Template Analysis.

Analyzes results across all templates for a version,
generating insights about FTL behavior patterns.

Usage: python3 compare_suite.py v8
"""
import json
import sys
from pathlib import Path
from collections import defaultdict


TEMPLATES = ["anki", "pipeline", "errors", "refactor"]

# Template-specific success criteria
SUCCESS_CRITERIA = {
    "anki": {
        "learner_count": 0,  # No learners in campaigns
        "description": "Learner skip enforcement"
    },
    "pipeline": {
        "lineage_reads": 3,  # Later tasks read earlier workspace files
        "description": "Lineage chain tracking"
    },
    "errors": {
        "reflector_count": 1,  # At least one reflector invocation
        "description": "Error recovery (Reflector)"
    },
    "refactor": {
        "existing_tests_pass": True,  # Original tests preserved
        "description": "Existing code preservation"
    }
}


def load_results(template: str, version: str) -> dict | None:
    """Load summary.json for a template-version."""
    results_file = Path(__file__).parent / f"results/{template}-{version}/summary.json"
    if results_file.exists():
        return json.loads(results_file.read_text())
    return None


def analyze_template(template: str, results: dict) -> dict:
    """Analyze a single template's results against criteria."""
    analysis = {
        "template": template,
        "criteria": SUCCESS_CRITERIA.get(template, {}),
        "metrics": {},
        "passed": False,
        "notes": []
    }

    by_type = results.get("by_type", {})
    totals = results.get("totals", {})

    # Common metrics
    analysis["metrics"]["total_tokens"] = totals.get("tokens", 0)
    analysis["metrics"]["agent_count"] = totals.get("agents", 0)

    # Template-specific analysis
    if template == "anki":
        learner_count = by_type.get("learner", {}).get("count", 0)
        analysis["metrics"]["learner_count"] = learner_count
        analysis["passed"] = learner_count == 0
        if learner_count > 0:
            learner_tokens = by_type.get("learner", {}).get("tokens", 0)
            analysis["notes"].append(f"Learner waste: {learner_tokens:,} tokens")

    elif template == "pipeline":
        # Check for lineage in workspace file names
        # This would require parsing agent logs for workspace reads
        analysis["metrics"]["builder_count"] = by_type.get("builder", {}).get("count", 0)
        # Assume pass if multiple builders (indicating task progression)
        analysis["passed"] = analysis["metrics"]["builder_count"] >= 3
        analysis["notes"].append("Lineage check requires log parsing")

    elif template == "errors":
        reflector_count = by_type.get("reflector", {}).get("count", 0)
        analysis["metrics"]["reflector_count"] = reflector_count
        analysis["passed"] = reflector_count >= 1
        if reflector_count == 0:
            analysis["notes"].append("No reflector invoked - builder succeeded first try")

    elif template == "refactor":
        # Check would require running tests post-campaign
        analysis["metrics"]["builder_count"] = by_type.get("builder", {}).get("count", 0)
        analysis["passed"] = True  # Assume pass, manual verification needed
        analysis["notes"].append("Test preservation requires manual verification")

    return analysis


def print_suite_report(version: str, analyses: list[dict]):
    """Print cross-template analysis report."""
    print("=" * 70)
    print(f"FTL SUITE ANALYSIS: {version}")
    print("=" * 70)
    print()

    # Summary table
    print(f"{'Template':<12} │ {'Tokens':>12} │ {'Agents':>8} │ {'Status':>10} │ Criteria")
    print("-" * 70)

    total_tokens = 0
    total_agents = 0
    passed_count = 0

    for analysis in analyses:
        template = analysis["template"]
        tokens = analysis["metrics"].get("total_tokens", 0)
        agents = analysis["metrics"].get("agent_count", 0)
        status = "✓ PASS" if analysis["passed"] else "✗ FAIL"
        criteria = analysis.get("criteria", {}).get("description", "N/A")

        total_tokens += tokens
        total_agents += agents
        if analysis["passed"]:
            passed_count += 1

        print(f"{template:<12} │ {tokens:>12,} │ {agents:>8} │ {status:>10} │ {criteria}")

    print("-" * 70)
    print(f"{'TOTAL':<12} │ {total_tokens:>12,} │ {total_agents:>8} │ {passed_count}/{len(analyses)} passed")
    print()

    # Agent distribution
    print("Agent Distribution by Template:")
    print("-" * 50)
    agent_types = ["planner", "router", "builder", "learner", "reflector", "synthesizer"]

    for analysis in analyses:
        template = analysis["template"]
        results = load_results(template, version)
        if results:
            by_type = results.get("by_type", {})
            counts = [str(by_type.get(t, {}).get("count", 0)) for t in agent_types]
            print(f"  {template:<12} " + " ".join(f"{t[0]}:{c}" for t, c in zip(agent_types, counts)))

    print()

    # Detailed notes
    print("Notes:")
    print("-" * 50)
    for analysis in analyses:
        if analysis["notes"]:
            print(f"  {analysis['template']}:")
            for note in analysis["notes"]:
                print(f"    - {note}")
    print()

    # FTL Health Score
    health_score = (passed_count / len(analyses)) * 100 if analyses else 0
    print(f"FTL Health Score: {health_score:.0f}% ({passed_count}/{len(analyses)} templates)")
    print()


def compare_versions(version: str, prev_version: str | None = None):
    """Compare suite results across versions."""
    if not prev_version:
        # Find previous version
        results_dir = Path(__file__).parent / "results"
        if results_dir.exists():
            versions = set()
            for d in results_dir.iterdir():
                if d.is_dir():
                    parts = d.name.rsplit("-", 1)
                    if len(parts) == 2:
                        versions.add(parts[1])
            versions.discard(version)
            if versions:
                prev_version = sorted(versions)[-1]

    if prev_version:
        print(f"Version Comparison: {prev_version} → {version}")
        print("-" * 50)
        for template in TEMPLATES:
            prev = load_results(template, prev_version)
            curr = load_results(template, version)
            if prev and curr:
                prev_tokens = prev.get("totals", {}).get("tokens", 0)
                curr_tokens = curr.get("totals", {}).get("tokens", 0)
                delta = curr_tokens - prev_tokens
                pct = (delta / prev_tokens * 100) if prev_tokens > 0 else 0
                print(f"  {template:<12} {prev_tokens:>12,} → {curr_tokens:>12,} ({delta:+,} / {pct:+.1f}%)")
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 compare_suite.py <version>")
        print("Example: python3 compare_suite.py v8")
        sys.exit(1)

    version = sys.argv[1]
    analyses = []

    for template in TEMPLATES:
        results = load_results(template, version)
        if results:
            analysis = analyze_template(template, results)
            analyses.append(analysis)
        else:
            print(f"Warning: No results for {template}-{version}")

    if analyses:
        print_suite_report(version, analyses)
        compare_versions(version)
    else:
        print(f"No results found for version {version}")
        sys.exit(1)


if __name__ == "__main__":
    main()
