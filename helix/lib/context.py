#!/usr/bin/env python3
"""Unified context builder for helix builders.

Builds memory-enriched context for builder agents. The key design:
1. Semantic search on objective (natural language)
2. Structured search on relevant files (file patterns)
3. Merge and dedupe with effectiveness ranking

The context is enrichment, not constraint. Builders are trusted
to do the right thing with good context.

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


def build_explorer_context(
    objective: str,
    scope: str,
    limit: int = 5
) -> dict:
    """Build context for explorer agents with known facts.

    Injects facts about codebase structure so explorers can
    skip rediscovering what's already known.

    Args:
        objective: User objective
        scope: Directory or area being explored
        limit: Maximum facts to inject

    Returns:
        {"known_facts": [...], "relevant_failures": [...], "injected": [...]}
    """
    # Query facts related to scope
    facts = recall(scope, type="fact", limit=limit, expand=False)

    # Also get any failures related to this area
    failures = recall(scope, type="failure", limit=3, expand=False)

    # Track injected memory names for feedback loop
    injected = [f["name"] for f in facts] + [f["name"] for f in failures]

    return {
        "known_facts": [
            f"{f['trigger']}" for f in facts
        ],
        "relevant_failures": [
            f"{f['trigger']} -> {f['resolution']}" for f in failures
        ],
        "injected": injected
    }


def build_planner_context(
    objective: str,
    limit: int = 5
) -> dict:
    """Build context for planner with decisions, conventions, evolution.

    Injects project context so planner makes consistent decisions
    and doesn't re-debate settled architectural choices.

    Args:
        objective: User objective
        limit: Maximum items per category

    Returns:
        {"decisions": [...], "conventions": [...], "recent_evolution": [...], "injected": [...]}
    """
    # Query each relevant type
    decisions = recall(objective, type="decision", limit=limit, expand=False)
    conventions = recall(objective, type="convention", limit=limit, expand=False)
    evolution = recall(objective, type="evolution", limit=limit, expand=False)

    # Track injected memory names for feedback loop
    injected = ([d["name"] for d in decisions] +
                [c["name"] for c in conventions] +
                [e["name"] for e in evolution])

    return {
        "decisions": [
            f"{d['trigger']}" for d in decisions
        ],
        "conventions": [
            f"[{d.get('effectiveness', 0.5):.0%}] {d['trigger']}" for d in conventions
        ],
        "recent_evolution": [
            f"{e['trigger']} - {e['resolution'][:80]}" for e in evolution
        ],
        "injected": injected
    }


def _query_by_type(objective: str, mem_type: str, limit: int = 2) -> List[dict]:
    """Query memory for specific type."""
    try:
        return recall(objective, type=mem_type, limit=limit, expand=False)
    except Exception:
        return []


def _query_facts_for_files(files: List[str], limit: int = 2) -> List[dict]:
    """Query facts related to specific files."""
    if not files:
        return []
    try:
        # Use file names as queries
        results = []
        seen = set()
        for f in files[:3]:  # Limit file queries
            for mem in recall(f, type="fact", limit=1, expand=False):
                if mem["name"] not in seen:
                    seen.add(mem["name"])
                    results.append(mem)
        return results[:limit]
    except Exception:
        return []


def _format_hint(memory: dict) -> str:
    """Format memory hint with confidence indicator.

    Includes effectiveness score so builders can weight advice:
    - [75%] = Memory helped 75% of the time
    - [unproven] = Not enough usage data yet
    """
    eff = memory.get("effectiveness", 0.5)
    helped = memory.get("helped", 0)
    failed = memory.get("failed", 0)

    # Show confidence only if we have actual usage data
    if helped + failed > 0:
        confidence = f"[{eff:.0%}]"
    else:
        confidence = "[unproven]"

    return f"{confidence} {memory['trigger']} -> {memory['resolution']}"


def build_context(
    task_data: dict,
    lineage: Optional[List[dict]] = None,
    memory_limit: int = 5,
    warning: Optional[str] = None
) -> dict:
    """Build unified context for helix-builder.

    Combines semantic search (on objective) with structured search
    (on relevant files) for comprehensive memory retrieval.

    Args:
        task_data: Dict with keys from TaskGet result:
            - subject: Task title (e.g., "001: impl-auth")
            - description: Task objective
            - metadata: {verify, framework, relevant_files}
        lineage: List of {seq, slug, delivered} from parent tasks
        memory_limit: Global budget for injected memories
        warning: Optional systemic issue warning from metacognition

    Returns:
        {
            "prompt": str - Formatted prompt for builder
            "injected": List[str] - Memory names injected (for feedback)
        }
    """
    lineage = lineage or []
    metadata = task_data.get("metadata", {})
    objective = task_data.get("description", "")
    relevant_files = metadata.get("relevant_files", [])

    # Query 1: Semantic search on objective (natural language works well)
    semantic_memories = _query_semantic(objective, limit=3)

    # Query 2: Structured search on relevant files (file patterns)
    file_memories = _query_by_files(relevant_files, limit=3)

    # Query 3: Conventions for this area
    conventions = _query_by_type(objective, "convention", limit=2)

    # Query 4: Facts about relevant files
    facts = _query_facts_for_files(relevant_files, limit=2)

    # Merge and dedupe with global budget
    all_memories = _merge_memories(semantic_memories, file_memories, limit=memory_limit)

    # Separate by type
    failures = [m for m in all_memories if m.get("type") == "failure"]
    patterns = [m for m in all_memories if m.get("type") == "pattern"]

    # Build complete injected list (includes conventions and facts)
    injected = list(set(
        [m["name"] for m in all_memories] +
        [c["name"] for c in conventions] +
        [f["name"] for f in facts]
    ))

    # Format for builder with confidence indicator
    failure_hints = [_format_hint(f) for f in failures]
    pattern_hints = [_format_hint(p) for p in patterns]
    convention_hints = [_format_hint(c) for c in conventions]
    fact_hints = [f"{f['trigger']}" for f in facts]

    # Build prompt with enrichment model
    prompt_lines = [
        f"TASK_ID: {task_data.get('id', '')}",
        f"TASK: {task_data.get('subject', '')}",
        f"OBJECTIVE: {objective}",
        f"VERIFY: {metadata.get('verify', '')}",
    ]

    # Add warning first if present (priority)
    if warning:
        prompt_lines.insert(0, f"WARNING: {warning}")

    # Add guidance fields (not constraints)
    if relevant_files:
        prompt_lines.append(f"RELEVANT_FILES: {json.dumps(relevant_files)}")

    framework = metadata.get("framework")
    if framework:
        prompt_lines.append(f"FRAMEWORK: {framework}")

    # Add memory-derived context
    prompt_lines.append(f"FAILURES_TO_AVOID: {json.dumps(failure_hints)}")
    prompt_lines.append(f"PATTERNS_TO_APPLY: {json.dumps(pattern_hints)}")

    # Add conventions and facts (new memory types)
    if convention_hints:
        prompt_lines.append(f"CONVENTIONS_TO_FOLLOW: {json.dumps(convention_hints)}")
    if fact_hints:
        prompt_lines.append(f"RELATED_FACTS: {json.dumps(fact_hints)}")

    prompt_lines.append(f"INJECTED_MEMORIES: {json.dumps(injected)}")

    if lineage:
        prompt_lines.append(f"PARENT_DELIVERIES: {json.dumps(lineage)}")

    prompt_lines.append("")
    prompt_lines.append("Execute this task following your builder protocol. Report DELIVERED or BLOCKED.")

    return {
        "prompt": "\n".join(prompt_lines),
        "injected": injected
    }


def _query_semantic(objective: str, limit: int = 3, expand: bool = True) -> List[dict]:
    """Query memory using semantic search on objective with graph expansion.

    Works well because objectives are natural language.
    Graph expansion (expand=True) surfaces solutions connected to relevant failures.
    """
    try:
        return recall(objective, limit=limit, expand=expand)
    except Exception:
        return []


def _query_by_files(relevant_files: List[str], limit: int = 3) -> List[dict]:
    """Query memory using structured file pattern matching.

    Complements semantic search for file-specific memories.
    """
    if not relevant_files:
        return []

    try:
        return recall_by_file_patterns(relevant_files, limit=limit)
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
            Each should have: subject, metadata.delivered_summary

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
        # Support both old and new field names
        delivered = metadata.get("delivered_summary") or metadata.get("delivered", "")

        if delivered:
            lineage.append({
                "seq": seq,
                "slug": slug,
                "delivered": delivered,
            })

    return lineage


# CLI for orchestrator usage
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Build execution context for builders")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-context
    p = subparsers.add_parser("build-context", help="Build full context from task data")
    p.add_argument("--task-data", required=True, help="JSON task data from TaskGet")
    p.add_argument("--lineage", default="[]", help="JSON lineage from parent tasks")
    p.add_argument("--memory-limit", type=int, default=5)
    p.add_argument("--warning", default=None, help="Systemic issue warning")

    # build-lineage
    p = subparsers.add_parser("build-lineage", help="Build lineage from completed blocker tasks")
    p.add_argument("--completed-tasks", required=True, help="JSON list of completed task data from TaskGet")

    # build-explorer-context
    p = subparsers.add_parser("build-explorer-context", help="Build context for explorer")
    p.add_argument("--objective", required=True)
    p.add_argument("--scope", required=True)
    p.add_argument("--limit", type=int, default=5)

    # build-planner-context
    p = subparsers.add_parser("build-planner-context", help="Build context for planner")
    p.add_argument("--objective", required=True)
    p.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()

    if args.command == "build-context":
        task_data = json.loads(args.task_data)
        lineage = json.loads(args.lineage)
        result = build_context(task_data, lineage, args.memory_limit, args.warning)
        print(json.dumps(result))

    elif args.command == "build-lineage":
        completed_tasks = json.loads(args.completed_tasks)
        result = build_lineage_from_tasks(completed_tasks)
        print(json.dumps(result))

    elif args.command == "build-explorer-context":
        result = build_explorer_context(args.objective, args.scope, args.limit)
        print(json.dumps(result))

    elif args.command == "build-planner-context":
        result = build_planner_context(args.objective, args.limit)
        print(json.dumps(result))



if __name__ == "__main__":
    _cli()
