"""Test FTL benchmark module."""

import json
import sys
from pathlib import Path

import pytest


class TestBenchmarkModule:
    """Test benchmark module functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, ftl_dir, monkeypatch):
        """Setup benchmark tests with temp directory."""
        self.ftl_dir = ftl_dir
        # Add lib to path
        lib_path = Path(__file__).parent.parent / "lib"
        monkeypatch.syspath_prepend(str(lib_path))

    def test_generate_test_memory(self):
        """Test synthetic memory generation."""
        from benchmark import generate_test_memory

        memory = generate_test_memory(num_failures=10, num_patterns=5)

        assert len(memory["failures"]) == 10
        assert len(memory["patterns"]) == 5
        assert all("name" in f for f in memory["failures"])
        assert all("trigger" in f for f in memory["failures"])
        assert all("created_at" in f for f in memory["failures"])

    def test_benchmark_result_dataclass(self):
        """Test BenchmarkResult dataclass."""
        from benchmark import BenchmarkResult

        # Without baseline
        result = BenchmarkResult(
            name="test",
            metric="time",
            value=10.5,
            unit="ms",
        )
        assert result.improvement is None

        # With baseline - improvement calculated
        result_with_baseline = BenchmarkResult(
            name="test",
            metric="time",
            value=8.0,
            unit="ms",
            baseline=10.0,
        )
        # (10 - 8) / 10 * 100 = 20%
        assert result_with_baseline.improvement == 20.0

    def test_benchmark_semantic_matching(self):
        """Test semantic matching benchmark runs."""
        from benchmark import benchmark_semantic_matching

        results = benchmark_semantic_matching()

        # Should return at least one result
        assert len(results) >= 1
        assert all(hasattr(r, 'name') for r in results)
        assert all(hasattr(r, 'value') for r in results)

    def test_benchmark_learning_simulation(self):
        """Test learning simulation benchmark."""
        from benchmark import benchmark_learning_simulation

        results = benchmark_learning_simulation(campaigns=5, tasks_per_campaign=3)

        # Should have results for baseline, memory-assisted, and improvement
        names = [r.name for r in results]
        assert "baseline_cost" in names
        assert "memory_assisted_cost" in names
        assert "efficiency_improvement" in names

        # Memory-assisted should be cheaper than baseline
        baseline = next(r for r in results if r.name == "baseline_cost")
        assisted = next(r for r in results if r.name == "memory_assisted_cost")
        assert assisted.value < baseline.value

    def test_generate_report(self):
        """Test report generation."""
        from benchmark import generate_report, run_all_benchmarks

        # Generate with explicit results
        results = {
            "retrieval": [],
            "semantic": [],
            "learning": [
                {"name": "efficiency_improvement", "value": 35.0, "unit": "%"},
            ],
            "pruning": [],
            "metadata": {
                "timestamp": "2026-01-16T10:00:00",
                "embeddings_available": True,
            }
        }

        report = generate_report(results)

        assert "FTL MEMORY BENCHMARK REPORT" in report
        assert "35.0%" in report
        assert "efficiency improvement" in report.lower()


class TestBenchmarkCLI:
    """Test benchmark CLI commands."""

    @pytest.fixture(autouse=True)
    def setup(self, ftl_dir, monkeypatch):
        """Setup for CLI tests."""
        self.ftl_dir = ftl_dir
        lib_path = Path(__file__).parent.parent / "lib"
        monkeypatch.syspath_prepend(str(lib_path))

    def test_cli_learning_command(self, capsys):
        """Test learning benchmark CLI command."""
        import benchmark

        # Run with minimal campaigns for speed
        results = benchmark.benchmark_learning_simulation(campaigns=2, tasks_per_campaign=2)

        # Should complete without error and return results
        assert len(results) > 0
