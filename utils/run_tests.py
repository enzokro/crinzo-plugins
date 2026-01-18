#!/usr/bin/env python3
"""
Parallel test runner for FTL tests.

Groups 158 tests by conceptual overlap and runs them concurrently using
subprocess workers. All tests are fully isolated (each gets its own tmp_path
+ SQLite database via conftest.py), so they can safely run in parallel.

Usage:
    python run_tests.py              # Run all groups in parallel
    python run_tests.py --group 2    # Run specific group only
    python run_tests.py --list       # List groups and exit
    python run_tests.py --verbose    # Show real-time output
"""

import argparse
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# Test file groupings by conceptual area
GROUPS: dict[int, list[str]] = {
    1: ["test_campaign.py"],  # Campaign lifecycle, DAG, cascade (47 tests)
    2: ["test_memory.py"],  # Memory system, semantic matching (32 tests)
    3: ["test_exploration.py", "test_benchmark.py"],  # Exploration, benchmarks (33 tests)
    4: ["test_observer.py", "test_workspace.py"],  # Observer, workspace CRUD (34 tests)
    5: ["test_integration.py"],  # Full workflows, CLI help (12 tests)
}

# Path to ftl/tests directory (relative to this script in utils/)
SCRIPT_DIR = Path(__file__).parent
TESTS_DIR = SCRIPT_DIR.parent / "ftl" / "tests"


@dataclass
class GroupResult:
    """Results from running a test group."""

    group_id: int
    files: list[str]
    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    stdout: str
    stderr: str
    returncode: int

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errors + self.skipped


def parse_pytest_output(output: str) -> tuple[int, int, int, int]:
    """
    Extract pass/fail/error/skipped counts from pytest output.

    Returns (passed, failed, errors, skipped).
    """
    passed = failed = errors = skipped = 0

    # Match patterns like "47 passed", "3 failed", "2 errors", "1 skipped"
    # Also handles combined lines like "45 passed, 2 failed"
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    error_match = re.search(r"(\d+) error", output)
    skipped_match = re.search(r"(\d+) skipped", output)

    if passed_match:
        passed = int(passed_match.group(1))
    if failed_match:
        failed = int(failed_match.group(1))
    if error_match:
        errors = int(error_match.group(1))
    if skipped_match:
        skipped = int(skipped_match.group(1))

    return passed, failed, errors, skipped


def run_group(
    group_id: int,
    files: list[str],
    xdist: bool = False,
    verbose: bool = False,
) -> GroupResult:
    """
    Run pytest for a group of test files.

    Args:
        group_id: The group number (for identification)
        files: List of test file names to run
        xdist: Enable pytest-xdist for additional parallelism within group
        verbose: Show output in real-time

    Returns:
        GroupResult with test outcomes and timing
    """
    start_time = time.time()

    # Build pytest command
    cmd = ["python", "-m", "pytest", "-v"]

    if xdist:
        cmd.extend(["-n", "auto"])

    # Add test files with full paths
    for f in files:
        cmd.append(str(TESTS_DIR / f))

    # Run pytest
    if verbose:
        # Real-time output - use Popen
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=TESTS_DIR.parent,  # Run from ftl directory
        )

        output_lines = []
        prefix = f"[G{group_id}] "

        for line in iter(process.stdout.readline, ""):
            print(f"{prefix}{line}", end="", flush=True)
            output_lines.append(line)

        process.wait()
        stdout = "".join(output_lines)
        stderr = ""
        returncode = process.returncode
    else:
        # Capture output for later display
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=TESTS_DIR.parent,
        )
        stdout = result.stdout
        stderr = result.stderr
        returncode = result.returncode

    duration = time.time() - start_time

    # Parse results
    passed, failed, errors, skipped = parse_pytest_output(stdout)

    return GroupResult(
        group_id=group_id,
        files=files,
        passed=passed,
        failed=failed,
        errors=errors,
        skipped=skipped,
        duration=duration,
        stdout=stdout,
        stderr=stderr,
        returncode=returncode,
    )


def run_parallel(
    groups: dict[int, list[str]],
    max_workers: int = 5,
    xdist: bool = False,
    verbose: bool = False,
) -> list[GroupResult]:
    """
    Run test groups in parallel using ThreadPoolExecutor.

    Args:
        groups: Mapping of group_id -> list of test files
        max_workers: Maximum parallel workers
        xdist: Enable pytest-xdist within groups
        verbose: Show real-time output

    Returns:
        List of GroupResult objects
    """
    results: list[GroupResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all groups
        futures = {
            executor.submit(run_group, gid, files, xdist, verbose): gid
            for gid, files in groups.items()
        }

        # Collect results as they complete
        for future in as_completed(futures):
            group_id = futures[future]
            try:
                result = future.result()
                results.append(result)

                # Progress indicator
                status = "PASS" if result.success else "FAIL"
                print(
                    f"Group {result.group_id} [{status}]: "
                    f"{result.passed} passed, {result.failed} failed, "
                    f"{result.errors} errors in {result.duration:.1f}s"
                )
            except Exception as e:
                print(f"Group {group_id} [ERROR]: {e}")
                # Create error result
                results.append(
                    GroupResult(
                        group_id=group_id,
                        files=groups[group_id],
                        passed=0,
                        failed=0,
                        errors=1,
                        skipped=0,
                        duration=0.0,
                        stdout="",
                        stderr=str(e),
                        returncode=-1,
                    )
                )

    return sorted(results, key=lambda r: r.group_id)


def print_summary(results: list[GroupResult], total_duration: float) -> None:
    """Print formatted summary table."""
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    # Header
    print(f"{'Group':<8} {'Files':<45} {'Pass':<6} {'Fail':<6} {'Time':<8}")
    print("-" * 70)

    total_passed = 0
    total_failed = 0
    total_errors = 0
    total_skipped = 0

    for r in results:
        files_str = ", ".join(r.files)
        if len(files_str) > 42:
            files_str = files_str[:39] + "..."

        status_icon = " " if r.success else "X"
        print(
            f"G{r.group_id:<6} {status_icon} {files_str:<43} "
            f"{r.passed:<6} {r.failed:<6} {r.duration:.1f}s"
        )

        total_passed += r.passed
        total_failed += r.failed
        total_errors += r.errors
        total_skipped += r.skipped

    print("-" * 70)
    print(
        f"{'TOTAL':<8} {'':<45} {total_passed:<6} {total_failed:<6} {total_duration:.1f}s"
    )
    print("=" * 70)

    # Final status
    if total_failed == 0 and total_errors == 0:
        print(f"\nAll {total_passed} tests passed!")
    else:
        print(f"\n{total_failed} failed, {total_errors} errors out of {total_passed + total_failed + total_errors} tests")

    if total_skipped > 0:
        print(f"({total_skipped} skipped)")


def print_failures(results: list[GroupResult]) -> None:
    """Print failure details for failed groups."""
    failed_groups = [r for r in results if not r.success]

    if not failed_groups:
        return

    print("\n" + "=" * 70)
    print("FAILURE DETAILS")
    print("=" * 70)

    for r in failed_groups:
        print(f"\n--- Group {r.group_id}: {', '.join(r.files)} ---")
        print(r.stdout)
        if r.stderr:
            print("STDERR:")
            print(r.stderr)


def list_groups() -> None:
    """List all groups and their test files."""
    print("Test Groups:")
    print("-" * 50)

    for gid, files in GROUPS.items():
        print(f"\nGroup {gid}:")
        for f in files:
            # Try to count tests in file
            test_file = TESTS_DIR / f
            if test_file.exists():
                content = test_file.read_text()
                test_count = len(re.findall(r"^\s*def test_", content, re.MULTILINE))
                print(f"  - {f} ({test_count} tests)")
            else:
                print(f"  - {f} (file not found)")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Parallel test runner for FTL tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--group",
        "-g",
        type=int,
        choices=list(GROUPS.keys()),
        help="Run specific group only",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=5,
        help="Maximum parallel workers (default: 5)",
    )
    parser.add_argument(
        "--xdist",
        "-x",
        action="store_true",
        help="Enable pytest-xdist within groups for additional parallelism",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show real-time output from tests",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List groups and exit",
    )
    parser.add_argument(
        "--show-failures",
        "-f",
        action="store_true",
        help="Show detailed failure output",
    )

    args = parser.parse_args()

    # Validate tests directory exists
    if not TESTS_DIR.exists():
        print(f"Error: Tests directory not found: {TESTS_DIR}")
        return 1

    # List mode
    if args.list:
        list_groups()
        return 0

    # Determine which groups to run
    if args.group:
        groups = {args.group: GROUPS[args.group]}
        print(f"Running group {args.group} only: {', '.join(groups[args.group])}")
    else:
        groups = GROUPS
        print(f"Running {len(groups)} groups with {args.workers} workers...")

    print()

    # Run tests
    start_time = time.time()

    if len(groups) == 1 or args.verbose:
        # Single group or verbose: run sequentially for cleaner output
        results = []
        for gid, files in groups.items():
            result = run_group(gid, files, args.xdist, args.verbose)
            results.append(result)
            if not args.verbose:
                status = "PASS" if result.success else "FAIL"
                print(
                    f"Group {result.group_id} [{status}]: "
                    f"{result.passed} passed, {result.failed} failed, "
                    f"{result.errors} errors in {result.duration:.1f}s"
                )
    else:
        # Parallel execution
        results = run_parallel(groups, args.workers, args.xdist, verbose=False)

    total_duration = time.time() - start_time

    # Print summary
    print_summary(results, total_duration)

    # Print failure details if requested or if there are failures
    if args.show_failures or any(not r.success for r in results):
        print_failures(results)

    # Exit code: 0 if all passed, 1 if any failed
    return 0 if all(r.success for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
