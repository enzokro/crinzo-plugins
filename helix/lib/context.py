#!/usr/bin/env python3
"""Unified context builder for helix builders.

Replaces the dual-path (build_prompt + hook) approach with a single
injection point that combines semantic and structured queries.

The key insight: semantic search on file paths doesn't work well because
embedding models are trained on natural language, not code paths.
This module uses BOTH:
1. Semantic search on objective (natural language)
2. Structured search on delta files (file patterns)

Usage:
    from lib.context import build_context

    result = build_context(task_data)
    # result["prompt"] - Formatted prompt for builder
    # result["injected"] - Memory names for feedback tracking
"""

import json
import sys
from pathlib import Path
from typing import List, Optional, Dict, Any

try:
    from .memory import recall, recall_by_file_patterns
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import recall, recall_by_file_patterns


def build_context(
    task_data: dict,
    lineage: Optional[List[dict]] = None,
    memory_limit: int = 5
) -> dict:
    """Build unified context for helix-builder.

    Combines semantic search (on objective) with structured search
    (on delta files) for comprehensive memory retrieval.

    This replaces the dual-path approach:
    - OLD: build_prompt() + hook injection (two tracking locations)
    - NEW: Single injection with both query types

    Args:
        task_data: Dict with keys from TaskGet result:
            - subject: Task title (e.g., "001: impl-auth")
            - description: Task objective
            - metadata: {delta, verify, budget, framework, idioms}
        lineage: List of {seq, slug, delivered} from parent tasks
        memory_limit: Global budget for injected memories

    Returns:
        {
            "prompt": str - Formatted prompt for builder
            "injected": List[str] - Memory names injected (for feedback)
        }
    """
    lineage = lineage or []
    metadata = task_data.get("metadata", {})
    objective = task_data.get("description", "")
    delta_files = metadata.get("delta", [])

    # Query 1: Semantic search on objective (natural language works well)
    semantic_memories = _query_semantic(objective, limit=3)

    # Query 2: Structured search on delta files (file patterns)
    file_memories = _query_by_files(delta_files, limit=3)

    # Merge and dedupe with global budget
    all_memories = _merge_memories(semantic_memories, file_memories, limit=memory_limit)

    # Separate by type
    failures = [m for m in all_memories if m.get("type") == "failure"]
    patterns = [m for m in all_memories if m.get("type") == "pattern"]
    injected = [m["name"] for m in all_memories]

    # Format for builder
    failure_hints = [
        f"{f['trigger']} -> {f['resolution']}"
        for f in failures
    ]
    pattern_hints = [
        f"{p['trigger']} -> {p['resolution']}"
        for p in patterns
    ]

    prompt = f"""TASK: {task_data.get("subject", "")}
OBJECTIVE: {objective}
DELTA: {json.dumps(delta_files)}
VERIFY: {metadata.get("verify", "")}
BUDGET: {metadata.get("budget", 7)}
FRAMEWORK: {metadata.get("framework") or "none"}
IDIOMS: {json.dumps(metadata.get("idioms", {}))}
FAILURES_TO_AVOID: {json.dumps(failure_hints)}
PATTERNS_TO_APPLY: {json.dumps(pattern_hints)}
INJECTED_MEMORIES: {json.dumps(injected)}
PARENT_DELIVERIES: {json.dumps(lineage)}

Execute this task following your builder protocol. Report DELIVERED or BLOCKED."""

    return {
        "prompt": prompt,
        "injected": injected
    }


def _query_semantic(objective: str, limit: int = 3) -> List[dict]:
    """Query memory using semantic search on objective.

    Works well because objectives are natural language.
    """
    try:
        return recall(objective, limit=limit)
    except Exception:
        return []


def _query_by_files(delta_files: List[str], limit: int = 3) -> List[dict]:
    """Query memory using structured file pattern matching.

    Complements semantic search for file-specific memories.
    """
    if not delta_files:
        return []

    try:
        return recall_by_file_patterns(delta_files, limit=limit)
    except Exception:
        return []


def _merge_memories(
    semantic: List[dict],
    files: List[dict],
    limit: int = 5
) -> List[dict]:
    """Merge and dedupe memories from both query paths.

    Prioritizes:
    1. High effectiveness (proven useful)
    2. Semantic matches (directly relevant to objective)
    3. File matches (relevant to specific files)

    Args:
        semantic: Memories from semantic search
        files: Memories from file pattern search
        limit: Global budget

    Returns:
        Deduplicated list of memories
    """
    seen_names = set()
    merged = []

    # First pass: semantic results (already ranked by score)
    for m in semantic:
        name = m.get("name")
        if name and name not in seen_names:
            seen_names.add(name)
            merged.append(m)

    # Second pass: file pattern results
    for m in files:
        name = m.get("name")
        if name and name not in seen_names:
            seen_names.add(name)
            merged.append(m)

    # Sort by effectiveness, take top N
    merged.sort(key=lambda m: m.get("effectiveness", 0.5), reverse=True)
    return merged[:limit]


def build_lineage_from_tasks(completed_tasks: List[dict]) -> List[dict]:
    """Build lineage list from completed blocker tasks.

    Args:
        completed_tasks: List of task data dicts from TaskGet calls
            Each should have: subject, metadata.delivered

    Returns:
        List of {seq, slug, delivered} for builder context
    """
    lineage = []
    for task in completed_tasks:
        subject = task.get("subject", "")
        # Parse "001: slug-name" format
        parts = subject.split(":", 1)
        seq = parts[0].strip() if parts else ""
        slug = parts[1].strip() if len(parts) > 1 else subject

        metadata = task.get("metadata", {})
        delivered = metadata.get("delivered", "")

        if delivered:
            lineage.append({
                "seq": seq,
                "slug": slug,
                "delivered": delivered,
            })

    return lineage


# Backwards compatibility alias
def build_prompt(
    task_data: dict,
    lineage: Optional[List[dict]] = None,
    memory_limit: int = 5
) -> dict:
    """Build the prompt string for helix-builder.

    DEPRECATED: Use build_context() instead.
    This function is kept for backwards compatibility.
    """
    return build_context(task_data, lineage, memory_limit)


# CLI for orchestrator usage
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Build execution context for builders")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-context (preferred)
    p = subparsers.add_parser("build-context", help="Build context from task data")
    p.add_argument("--task-data", required=True, help="JSON task data from TaskGet")
    p.add_argument("--lineage", default="[]", help="JSON lineage from parent tasks")
    p.add_argument("--memory-limit", type=int, default=5)

    # build-prompt (deprecated, kept for compatibility)
    p = subparsers.add_parser("build-prompt", help="Build prompt (deprecated, use build-context)")
    p.add_argument("--task-data", required=True, help="JSON task data from TaskGet")
    p.add_argument("--lineage", default="[]", help="JSON lineage from parent tasks")
    p.add_argument("--memory-limit", type=int, default=5)

    args = parser.parse_args()

    if args.command in ("build-context", "build-prompt"):
        task_data = json.loads(args.task_data)
        lineage = json.loads(args.lineage)
        result = build_context(task_data, lineage, args.memory_limit)
        print(json.dumps(result))


if __name__ == "__main__":
    _cli()
