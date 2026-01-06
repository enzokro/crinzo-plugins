#!/usr/bin/env python3
"""Compare two FTL campaign runs.

Usage: python3 compare.py v7 v8
"""
import json
import sys
from pathlib import Path


def load_results(version: str) -> dict:
    """Load results from summary.json."""
    results_file = Path(__file__).parent / f"results/{version}/summary.json"
    if results_file.exists():
        return json.loads(results_file.read_text())
    print(f"Error: {results_file} not found")
    sys.exit(1)


def compare(v1: str, v2: str):
    """Compare two versions."""
    r1 = load_results(v1)
    r2 = load_results(v2)

    print("=" * 65)
    print(f"COMPARISON: {v1} -> {v2}")
    print("=" * 65)

    print(f"\n{'Agent':<12} | {v1:>12} | {v2:>12} | {'Delta':>12} | {'%':>8}")
    print("-" * 65)

    for atype in ["planner", "router", "builder", "learner", "synthesizer"]:
        t1 = r1["by_type"].get(atype, {}).get("tokens", 0)
        t2 = r2["by_type"].get(atype, {}).get("tokens", 0)
        delta = t2 - t1
        pct = f"{delta/t1*100:+.1f}%" if t1 > 0 else "N/A"
        marker = " !!!" if atype == "learner" and t2 > 0 else ""
        print(
            f"{atype:<12} | {t1:>12,} | {t2:>12,} | {delta:>+12,} | {pct:>8}{marker}"
        )

    print("-" * 65)
    t1 = r1["totals"]["tokens"]
    t2 = r2["totals"]["tokens"]
    delta = t2 - t1
    print(f"{'TOTAL':<12} | {t1:>12,} | {t2:>12,} | {delta:>+12,} | {delta/t1*100:+.1f}%")

    # Learner analysis
    l1 = r1["by_type"].get("learner", {}).get("count", 0)
    l2 = r2["by_type"].get("learner", {}).get("count", 0)
    if l1 > 0 and l2 == 0:
        print(f"\n[OK] Learner removal SUCCESS: {l1} -> {l2}")
    elif l2 > 0:
        print(f"\n!!! Learner still present: {l2} agents")
    elif l1 == 0 and l2 == 0:
        print(f"\n[OK] No learners in either version")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 compare.py <version1> <version2>")
        print("Example: python3 compare.py v7 v8")
        sys.exit(1)
    compare(sys.argv[1], sys.argv[2])
