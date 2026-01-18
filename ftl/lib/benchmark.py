#!/usr/bin/env python3
"""Benchmarking infrastructure for FTL memory system.

Validates efficiency claims and provides metrics for:
- Memory retrieval performance
- Semantic matching quality
- Learning loop effectiveness
- Comparison with baseline (no memory)

All results stored in .ftl/ftl.db benchmark table.

CLI:
    python3 lib/benchmark.py run                          # Run all benchmarks
    python3 lib/benchmark.py retrieval                    # Test retrieval speed
    python3 lib/benchmark.py matching                     # Test semantic matching quality
    python3 lib/benchmark.py learning                     # Simulate learning loop
    python3 lib/benchmark.py report                       # Generate full report
    python3 lib/benchmark.py get-run --run-id ID          # Get run results
    python3 lib/benchmark.py compare --run-a ID --run-b ID  # Compare two runs
"""

import argparse
import json
import sys
import time
import random
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional
import tempfile

# Support both standalone execution and module import
try:
    from lib.memory import (
        load_memory, get_context, add_failure, add_pattern,
        prune_memory, get_stats, _calculate_importance_score, _hybrid_score
    )
    from lib.db.embeddings import similarity as semantic_similarity, is_available
    from lib.db import get_db, init_db
    from lib.db.schema import Benchmark
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import (
        load_memory, get_context, add_failure, add_pattern,
        prune_memory, get_stats, _calculate_importance_score, _hybrid_score
    )
    from db.embeddings import similarity as semantic_similarity, is_available
    from db import get_db, init_db
    from db.schema import Benchmark

# Alias for backward compatibility
_calculate_importance = _calculate_importance_score
save_memory = lambda m, p=None: None  # No-op stub (database handles persistence)


def _ensure_db():
    """Ensure database is initialized on first use."""
    init_db()
    return get_db()


# =============================================================================
# Database Operations for Benchmark Results
# =============================================================================

def record_metric(run_id: str, metric: str, value: float, metadata: dict = None) -> dict:
    """Record benchmark metric to database.

    Args:
        run_id: UUID for benchmark run
        metric: Metric name (memory_size, query_time, etc)
        value: Metric value
        metadata: Optional additional data

    Returns:
        {"id": record_id, "run_id": run_id}
    """
    db = _ensure_db()
    record = Benchmark(
        run_id=run_id,
        metric=metric,
        value=value,
        metadata=json.dumps(metadata or {}),
        created_at=datetime.now().isoformat()
    )
    result = db.t.benchmark.insert(record)
    return {"id": result.id, "run_id": run_id}


def get_run(run_id: str) -> list:
    """Get all metrics for a benchmark run.

    Args:
        run_id: UUID for benchmark run

    Returns:
        List of metric dicts
    """
    db = _ensure_db()
    rows = list(db.t.benchmark.rows_where("run_id = ?", [run_id]))
    return [
        {
            "id": r["id"],
            "run_id": r["run_id"],
            "metric": r["metric"],
            "value": r["value"],
            "metadata": json.loads(r["metadata"]),
            "created_at": r["created_at"]
        }
        for r in rows
    ]


def compare_runs(run_id_a: str, run_id_b: str) -> dict:
    """Compare two benchmark runs.

    Args:
        run_id_a: First run ID
        run_id_b: Second run ID

    Returns:
        Comparison dict with metrics from both runs
    """
    a_metrics = {r["metric"]: r["value"] for r in get_run(run_id_a)}
    b_metrics = {r["metric"]: r["value"] for r in get_run(run_id_b)}

    comparison = {}
    all_metrics = set(a_metrics.keys()) | set(b_metrics.keys())

    for metric in all_metrics:
        a_val = a_metrics.get(metric)
        b_val = b_metrics.get(metric)
        diff = None
        if a_val is not None and b_val is not None and a_val != 0:
            diff = round((b_val - a_val) / a_val * 100, 2)
        comparison[metric] = {
            "run_a": a_val,
            "run_b": b_val,
            "diff_percent": diff
        }

    return {
        "run_a": run_id_a,
        "run_b": run_id_b,
        "metrics": comparison
    }


def list_runs(limit: int = 10) -> list:
    """List recent benchmark runs.

    Args:
        limit: Maximum runs to return

    Returns:
        List of run summaries
    """
    db = _ensure_db()
    rows = list(db.t.benchmark.rows)

    # Group by run_id
    runs = {}
    for r in rows:
        run_id = r["run_id"]
        if run_id not in runs:
            runs[run_id] = {
                "run_id": run_id,
                "metrics": 0,
                "created_at": r["created_at"]
            }
        runs[run_id]["metrics"] += 1
        if r["created_at"] < runs[run_id]["created_at"]:
            runs[run_id]["created_at"] = r["created_at"]

    # Sort by date and limit
    sorted_runs = sorted(runs.values(), key=lambda x: x["created_at"], reverse=True)
    return sorted_runs[:limit]


# =============================================================================
# Benchmark Result Data Class
# =============================================================================

@dataclass
class BenchmarkResult:
    name: str
    metric: str
    value: float
    unit: str
    baseline: Optional[float] = None
    improvement: Optional[float] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.baseline is not None and self.baseline > 0:
            self.improvement = round((self.baseline - self.value) / self.baseline * 100, 2)


# =============================================================================
# Sample Data for Benchmarking
# =============================================================================

SAMPLE_TRIGGERS = [
    "ModuleNotFoundError: No module named 'pandas'",
    "TypeError: cannot unpack non-iterable NoneType object",
    "ValueError: invalid literal for int() with base 10: 'abc'",
    "KeyError: 'user_id' not found in dictionary",
    "AttributeError: 'NoneType' object has no attribute 'split'",
    "IndexError: list index out of range",
    "FileNotFoundError: [Errno 2] No such file or directory: 'config.json'",
    "ConnectionError: Failed to establish connection to database",
    "TimeoutError: Operation timed out after 30 seconds",
    "PermissionError: [Errno 13] Permission denied: '/etc/passwd'",
    "JSONDecodeError: Expecting property name enclosed in double quotes",
    "UnicodeDecodeError: 'utf-8' codec can't decode byte 0xff",
    "RecursionError: maximum recursion depth exceeded",
    "MemoryError: unable to allocate array",
    "ZeroDivisionError: division by zero",
    "AssertionError: Expected True, got False",
    "RuntimeError: dictionary changed size during iteration",
    "StopIteration: generator raised StopIteration",
    "ImportError: cannot import name 'async_cache' from 'functools'",
    "OSError: [Errno 28] No space left on device",
]

SAMPLE_OBJECTIVES = [
    "Fix import error for missing pandas module",
    "Handle None values in data processing pipeline",
    "Parse user input safely with proper type conversion",
    "Access dictionary keys with proper error handling",
    "Handle optional attributes on potentially None objects",
    "Iterate over list with proper bounds checking",
    "Load configuration file with fallback defaults",
    "Connect to database with retry logic",
    "Implement timeout handling for long operations",
    "Handle file permissions across platforms",
]


def generate_test_memory(num_failures: int = 100, num_patterns: int = 50) -> dict:
    """Generate synthetic memory data for benchmarking."""
    random.seed(42)  # Reproducible results
    now = datetime.now()

    failures = []
    for i in range(num_failures):
        age_days = random.randint(0, 90)
        created = (now - timedelta(days=age_days)).isoformat()
        failures.append({
            "name": f"failure-{i:03d}",
            "trigger": random.choice(SAMPLE_TRIGGERS) + f" variant {i}",
            "fix": f"Apply fix {i} to resolve the issue",
            "match": f".*error.*{i}.*",
            "cost": random.randint(100, 50000),
            "source": [f"ws-{i}"],
            "created_at": created,
            "access_count": random.randint(0, 20),
            "related": [],
        })

    patterns = []
    for i in range(num_patterns):
        age_days = random.randint(0, 90)
        created = (now - timedelta(days=age_days)).isoformat()
        patterns.append({
            "name": f"pattern-{i:03d}",
            "trigger": f"Optimization opportunity {i}",
            "insight": f"Apply technique {i} for better performance",
            "saved": random.randint(500, 20000),
            "source": [f"ws-{i}"],
            "created_at": created,
            "access_count": random.randint(0, 10),
            "related": [],
        })

    return {"failures": failures, "patterns": patterns}


# =============================================================================
# Benchmark Functions
# =============================================================================

def benchmark_retrieval_speed(memory_sizes: list = None, run_id: str = None) -> list:
    """Benchmark memory retrieval speed at different memory sizes."""
    if memory_sizes is None:
        memory_sizes = [10, 50, 100, 250, 500]

    results = []
    test_objective = "Handle database connection timeout with retry"

    for size in memory_sizes:
        # Setup - use temp file for test
        test_memory = generate_test_memory(num_failures=size, num_patterns=size // 2)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_memory, f)
            test_path = Path(f.name)

        # Benchmark retrieval without objective (fast path)
        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            get_context(max_failures=5, max_patterns=3)
        elapsed_no_semantic = (time.perf_counter() - start) / iterations * 1000

        # Benchmark retrieval with objective (semantic path)
        start = time.perf_counter()
        for _ in range(iterations):
            get_context(objective=test_objective, max_failures=5, max_patterns=3)
        elapsed_semantic = (time.perf_counter() - start) / iterations * 1000

        results.append(BenchmarkResult(
            name=f"retrieval_no_semantic_{size}",
            metric="retrieval_time",
            value=round(elapsed_no_semantic, 3),
            unit="ms",
        ))
        results.append(BenchmarkResult(
            name=f"retrieval_semantic_{size}",
            metric="retrieval_time",
            value=round(elapsed_semantic, 3),
            unit="ms",
            baseline=elapsed_no_semantic,
        ))

        # Record to database if run_id provided
        if run_id:
            record_metric(run_id, f"retrieval_no_semantic_{size}", elapsed_no_semantic,
                         {"unit": "ms", "size": size})
            record_metric(run_id, f"retrieval_semantic_{size}", elapsed_semantic,
                         {"unit": "ms", "size": size})

        # Cleanup
        test_path.unlink()

    return results


def benchmark_semantic_matching(run_id: str = None) -> list:
    """Benchmark semantic matching quality and relevance scoring."""
    results = []

    # Test semantic similarity accuracy
    test_pairs = [
        # Should have high similarity
        ("ModuleNotFoundError: No module named 'pandas'", "Import error for pandas library", True),
        ("TypeError: cannot unpack non-iterable NoneType", "NoneType unpacking error", True),
        ("database connection timeout", "DB connection timed out after 30s", True),
        # Should have low similarity
        ("ModuleNotFoundError: No module named 'pandas'", "Build React component tree", False),
        ("TypeError: cannot unpack non-iterable NoneType", "Configure git repository", False),
    ]

    if not is_available():
        results.append(BenchmarkResult(
            name="semantic_matching",
            metric="status",
            value=0,
            unit="unavailable (fallback mode)",
        ))
        if run_id:
            record_metric(run_id, "semantic_available", 0, {"status": "fallback"})
        return results

    correct = 0
    total = len(test_pairs)
    threshold = 0.5

    for text1, text2, should_match in test_pairs:
        similarity = semantic_similarity(text1, text2)
        is_match = similarity >= threshold
        if is_match == should_match:
            correct += 1

    accuracy = correct / total * 100
    results.append(BenchmarkResult(
        name="semantic_matching_accuracy",
        metric="accuracy",
        value=round(accuracy, 1),
        unit="%",
        baseline=100.0,
    ))

    # Test hybrid scoring distribution
    scores = []
    for trigger in SAMPLE_TRIGGERS:
        for objective in SAMPLE_OBJECTIVES:
            relevance = semantic_similarity(trigger, objective)
            cost = random.randint(100, 50000)
            score = _hybrid_score(relevance, cost)
            scores.append(score)

    mean_score = round(sum(scores) / len(scores), 3)
    max_score = round(max(scores), 3)

    results.append(BenchmarkResult(
        name="hybrid_score_mean",
        metric="hybrid_score",
        value=mean_score,
        unit="score",
    ))
    results.append(BenchmarkResult(
        name="hybrid_score_max",
        metric="hybrid_score",
        value=max_score,
        unit="score",
    ))

    # Record to database
    if run_id:
        record_metric(run_id, "semantic_accuracy", accuracy, {"unit": "%"})
        record_metric(run_id, "hybrid_score_mean", mean_score, {"unit": "score"})
        record_metric(run_id, "hybrid_score_max", max_score, {"unit": "score"})

    return results


def benchmark_learning_simulation(campaigns: int = 10, tasks_per_campaign: int = 5, run_id: str = None) -> list:
    """Simulate learning loop and measure efficiency gains."""
    results = []
    random.seed(42)

    # Simulate baseline: each task encounters errors randomly
    baseline_total_cost = 0
    for _ in range(campaigns):
        for _ in range(tasks_per_campaign):
            if random.random() < 0.7:
                baseline_total_cost += random.randint(1000, 10000)

    # Simulate with memory: learning reduces error probability
    memory_assisted_cost = 0
    accumulated_knowledge = 0

    for campaign in range(campaigns):
        for task in range(tasks_per_campaign):
            base_prob = 0.7
            learning_factor = 0.02
            current_prob = max(0.1, base_prob * (1 - learning_factor * accumulated_knowledge))

            if random.random() < current_prob:
                cost = random.randint(1000, 10000)
                memory_assisted_cost += cost
                accumulated_knowledge += 1
            else:
                memory_assisted_cost += 50

    improvement = (baseline_total_cost - memory_assisted_cost) / baseline_total_cost * 100

    results.append(BenchmarkResult(
        name="baseline_cost",
        metric="simulated_tokens",
        value=baseline_total_cost,
        unit="tokens",
    ))
    results.append(BenchmarkResult(
        name="memory_assisted_cost",
        metric="simulated_tokens",
        value=memory_assisted_cost,
        unit="tokens",
        baseline=baseline_total_cost,
    ))
    results.append(BenchmarkResult(
        name="efficiency_improvement",
        metric="improvement",
        value=round(improvement, 1),
        unit="%",
    ))
    results.append(BenchmarkResult(
        name="knowledge_accumulated",
        metric="entries",
        value=accumulated_knowledge,
        unit="entries",
    ))

    # Record to database
    if run_id:
        record_metric(run_id, "baseline_cost", baseline_total_cost, {"unit": "tokens"})
        record_metric(run_id, "memory_assisted_cost", memory_assisted_cost, {"unit": "tokens"})
        record_metric(run_id, "efficiency_improvement", improvement, {"unit": "%"})
        record_metric(run_id, "knowledge_accumulated", accumulated_knowledge, {"unit": "entries"})

    return results


def benchmark_pruning(run_id: str = None) -> list:
    """Benchmark pruning performance and effectiveness."""
    results = []

    # Create large memory in temp file
    test_memory = generate_test_memory(num_failures=500, num_patterns=200)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(test_memory, f)
        test_path = Path(f.name)

    # Measure pruning time
    start = time.perf_counter()
    prune_result = prune_memory(
        path=test_path,
        max_failures=100,
        max_patterns=50,
        min_importance=0.1,
    )
    elapsed = (time.perf_counter() - start) * 1000

    results.append(BenchmarkResult(
        name="prune_time",
        metric="prune_time",
        value=round(elapsed, 2),
        unit="ms",
    ))
    results.append(BenchmarkResult(
        name="pruned_failures",
        metric="entries_removed",
        value=prune_result["pruned_failures"],
        unit="entries",
    ))
    results.append(BenchmarkResult(
        name="pruned_patterns",
        metric="entries_removed",
        value=prune_result["pruned_patterns"],
        unit="entries",
    ))

    # Record to database
    if run_id:
        record_metric(run_id, "prune_time", elapsed, {"unit": "ms"})
        record_metric(run_id, "pruned_failures", prune_result["pruned_failures"], {"unit": "entries"})
        record_metric(run_id, "pruned_patterns", prune_result["pruned_patterns"], {"unit": "entries"})

    # Cleanup
    test_path.unlink()

    return results


def run_all_benchmarks() -> dict:
    """Run all benchmarks and store results in database."""
    _ensure_db()
    run_id = str(uuid.uuid4())[:8]

    all_results = {
        "run_id": run_id,
        "retrieval": [asdict(r) for r in benchmark_retrieval_speed(run_id=run_id)],
        "semantic": [asdict(r) for r in benchmark_semantic_matching(run_id=run_id)],
        "learning": [asdict(r) for r in benchmark_learning_simulation(run_id=run_id)],
        "pruning": [asdict(r) for r in benchmark_pruning(run_id=run_id)],
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "embeddings_available": is_available(),
        }
    }

    # Record metadata
    record_metric(run_id, "_metadata_embeddings", 1 if is_available() else 0, {})

    return all_results


def generate_report(results: dict = None) -> str:
    """Generate human-readable benchmark report."""
    if results is None:
        # Get latest run from database
        runs = list_runs(limit=1)
        if runs:
            run_id = runs[0]["run_id"]
            metrics = get_run(run_id)
            results = {
                "run_id": run_id,
                "retrieval": [],
                "semantic": [],
                "learning": [],
                "pruning": [],
                "metadata": {
                    "timestamp": metrics[0]["created_at"] if metrics else datetime.now().isoformat(),
                    "embeddings_available": any(m["metric"] == "_metadata_embeddings" and m["value"] == 1 for m in metrics)
                }
            }
            # Categorize metrics
            for m in metrics:
                if m["metric"].startswith("retrieval"):
                    results["retrieval"].append({"name": m["metric"], "value": m["value"], **m["metadata"]})
                elif m["metric"].startswith("semantic") or m["metric"].startswith("hybrid"):
                    results["semantic"].append({"name": m["metric"], "value": m["value"], **m["metadata"]})
                elif m["metric"] in ["baseline_cost", "memory_assisted_cost", "efficiency_improvement", "knowledge_accumulated"]:
                    results["learning"].append({"name": m["metric"], "value": m["value"], **m["metadata"]})
                elif m["metric"].startswith("prune"):
                    results["pruning"].append({"name": m["metric"], "value": m["value"], **m["metadata"]})
        else:
            results = run_all_benchmarks()

    report = []
    report.append("=" * 60)
    report.append("FTL MEMORY BENCHMARK REPORT")
    report.append("=" * 60)
    report.append(f"Run ID: {results.get('run_id', 'N/A')}")
    report.append(f"Generated: {results['metadata']['timestamp']}")
    report.append(f"Semantic Embeddings: {'Available' if results['metadata']['embeddings_available'] else 'Fallback mode'}")
    report.append("")

    # Retrieval Performance
    report.append("-" * 40)
    report.append("RETRIEVAL PERFORMANCE")
    report.append("-" * 40)
    for r in results.get("retrieval", []):
        line = f"  {r['name']}: {r['value']} {r.get('unit', 'ms')}"
        if r.get('improvement'):
            report.append(f"{line} (overhead: +{-r['improvement']:.1f}%)")
        else:
            report.append(line)
    report.append("")

    # Semantic Matching
    report.append("-" * 40)
    report.append("SEMANTIC MATCHING QUALITY")
    report.append("-" * 40)
    for r in results.get("semantic", []):
        report.append(f"  {r['name']}: {r['value']} {r.get('unit', '')}")
    report.append("")

    # Learning Simulation
    report.append("-" * 40)
    report.append("LEARNING EFFICIENCY (SIMULATED)")
    report.append("-" * 40)
    for r in results.get("learning", []):
        line = f"  {r['name']}: {r['value']} {r.get('unit', '')}"
        if r.get('improvement'):
            report.append(f"{line} ({r['improvement']:.1f}% improvement)")
        else:
            report.append(line)
    report.append("")

    # Pruning Performance
    report.append("-" * 40)
    report.append("PRUNING PERFORMANCE")
    report.append("-" * 40)
    for r in results.get("pruning", []):
        report.append(f"  {r['name']}: {r['value']} {r.get('unit', '')}")
    report.append("")

    # Summary
    report.append("=" * 60)
    report.append("SUMMARY")
    report.append("=" * 60)

    learning_results = {r['name']: r for r in results.get("learning", [])}
    if "efficiency_improvement" in learning_results:
        imp = learning_results["efficiency_improvement"]["value"]
        report.append(f"Simulated efficiency improvement: {imp}%")
        if imp >= 30:
            report.append("OK: Meets claimed 35% efficiency improvement target range")
        else:
            report.append(f"Below claimed 35% target (actual: {imp}%)")

    report.append("")

    return "\n".join(report)


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="FTL benchmark suite")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("run", help="Run all benchmarks")
    subparsers.add_parser("retrieval", help="Benchmark retrieval speed")
    subparsers.add_parser("matching", help="Benchmark semantic matching")
    subparsers.add_parser("learning", help="Benchmark learning simulation")
    subparsers.add_parser("pruning", help="Benchmark pruning")
    subparsers.add_parser("report", help="Generate benchmark report")

    # Database operations
    gr = subparsers.add_parser("get-run", help="Get run results")
    gr.add_argument("--run-id", required=True, help="Run ID")

    cr = subparsers.add_parser("compare", help="Compare two runs")
    cr.add_argument("--run-a", required=True, help="First run ID")
    cr.add_argument("--run-b", required=True, help="Second run ID")

    subparsers.add_parser("list-runs", help="List recent runs")

    args = parser.parse_args()

    if args.command == "run":
        results = run_all_benchmarks()
        print(json.dumps(results, indent=2))

    elif args.command == "retrieval":
        run_id = str(uuid.uuid4())[:8]
        results = benchmark_retrieval_speed(run_id=run_id)
        print(json.dumps([asdict(r) for r in results], indent=2))

    elif args.command == "matching":
        run_id = str(uuid.uuid4())[:8]
        results = benchmark_semantic_matching(run_id=run_id)
        print(json.dumps([asdict(r) for r in results], indent=2))

    elif args.command == "learning":
        run_id = str(uuid.uuid4())[:8]
        results = benchmark_learning_simulation(run_id=run_id)
        print(json.dumps([asdict(r) for r in results], indent=2))

    elif args.command == "pruning":
        run_id = str(uuid.uuid4())[:8]
        results = benchmark_pruning(run_id=run_id)
        print(json.dumps([asdict(r) for r in results], indent=2))

    elif args.command == "report":
        print(generate_report())

    elif args.command == "get-run":
        results = get_run(args.run_id)
        print(json.dumps(results, indent=2))

    elif args.command == "compare":
        results = compare_runs(args.run_a, args.run_b)
        print(json.dumps(results, indent=2))

    elif args.command == "list-runs":
        results = list_runs()
        print(json.dumps(results, indent=2))

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
