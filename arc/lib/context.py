#!/usr/bin/env python3
"""Context builder for the REASON phase.

Gathers everything needed for adaptive reasoning:
- Memory (what we know)
- Codebase signals (quick assessment)
- Complexity signals (how deep to think)
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

try:
    from . import memory
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    import memory


def build(objective: str, quick: bool = False) -> dict:
    """Build context for reasoning.

    Args:
        objective: What the user wants to accomplish
        quick: If True, skip codebase assessment (for simple queries)

    Returns context dict with memory, codebase, and complexity signals.
    """
    ctx = {
        "objective": objective,
        "memory": _gather_memory(objective),
        "codebase": {} if quick else _assess_codebase(objective),
        "complexity": _assess_complexity(objective),
    }

    return ctx


def _gather_memory(objective: str) -> dict:
    """Query memory for relevant knowledge."""
    failures = memory.recall(objective, type="failure", limit=5)
    patterns = memory.recall(objective, type="pattern", limit=3)

    # Get connected knowledge for top results
    connected = []
    for m in (failures[:2] + patterns[:1]):
        related = memory.connected(m["name"], max_hops=1)
        connected.extend(related)

    # Deduplicate
    seen = {m["name"] for m in failures + patterns}
    connected = [c for c in connected if c["name"] not in seen][:3]

    return {
        "failures": failures,
        "patterns": patterns,
        "connected": connected,
        "injected_names": [m["name"] for m in failures + patterns + connected]
    }


def _assess_codebase(objective: str) -> dict:
    """Quick codebase assessment."""
    codebase = {
        "has_tests": False,
        "has_src": False,
        "languages": [],
        "framework_hints": [],
        "relevant_files": []
    }

    # Check directory structure
    cwd = Path.cwd()

    if (cwd / "tests").exists() or (cwd / "test").exists():
        codebase["has_tests"] = True

    if (cwd / "src").exists() or (cwd / "lib").exists():
        codebase["has_src"] = True

    # Check for common files
    for pattern, lang in [("*.py", "python"), ("*.js", "javascript"), ("*.ts", "typescript"), ("*.go", "go"), ("*.rs", "rust")]:
        if list(cwd.glob(f"**/{pattern}"))[:1]:
            codebase["languages"].append(lang)

    # Framework hints from common files
    hints = [
        ("requirements.txt", "python"),
        ("pyproject.toml", "python"),
        ("package.json", "node"),
        ("Cargo.toml", "rust"),
        ("go.mod", "go"),
    ]
    for fname, hint in hints:
        if (cwd / fname).exists():
            codebase["framework_hints"].append(hint)

    # Quick grep for objective keywords
    keywords = _extract_keywords(objective)
    if keywords:
        relevant = _find_relevant_files(keywords)
        codebase["relevant_files"] = relevant[:5]

    return codebase


def _assess_complexity(objective: str) -> dict:
    """Assess how complex this objective is."""
    signals = {
        "word_count": len(objective.split()),
        "has_multiple_parts": any(w in objective.lower() for w in ["and", "then", "also", "plus"]),
        "mentions_files": any(w in objective.lower() for w in ["file", "module", "class", "function"]),
        "is_question": objective.strip().endswith("?"),
        "is_fix": any(w in objective.lower() for w in ["fix", "bug", "error", "issue", "broken"]),
        "is_add": any(w in objective.lower() for w in ["add", "create", "implement", "build", "make"]),
        "is_change": any(w in objective.lower() for w in ["change", "modify", "update", "refactor"]),
    }

    # Estimate complexity level
    level = "simple"
    if signals["word_count"] > 20 or signals["has_multiple_parts"]:
        level = "moderate"
    if signals["word_count"] > 40 or (signals["has_multiple_parts"] and signals["mentions_files"]):
        level = "complex"

    signals["level"] = level
    signals["suggested_decomposition"] = level != "simple"

    return signals


def _extract_keywords(text: str) -> list:
    """Extract meaningful keywords from text."""
    stop = {"the", "a", "an", "to", "for", "in", "on", "with", "and", "or", "is", "are", "be", "this", "that", "it"}
    words = text.lower().split()
    return [w for w in words if len(w) > 2 and w not in stop][:5]


def _find_relevant_files(keywords: list) -> list:
    """Find files that might be relevant to keywords."""
    try:
        cmd = ["grep", "-rl", "--include=*.py", "--include=*.js", "--include=*.ts", "|".join(keywords), "."]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return result.stdout.strip().split("\n")[:5]
    except:
        pass
    return []


# CLI
if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("objective")
    p.add_argument("--quick", action="store_true")
    args = p.parse_args()

    ctx = build(args.objective, args.quick)
    print(json.dumps(ctx, indent=2))
