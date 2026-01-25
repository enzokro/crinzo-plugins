#!/usr/bin/env python3
"""Context builder for helix builders.

Replaces lib/workspace.py. No database storage - context is built
on-demand from TaskGet data + memory.recall.

The orchestrator (SKILL.md) calls TaskGet to retrieve task metadata,
then uses this module to build the prompt string for helix-builder.
"""

import json
import sys
from pathlib import Path
from typing import List, Optional

try:
    from .memory import recall
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import recall


def build_prompt(
    task_data: dict,
    lineage: Optional[List[dict]] = None,
    memory_limit: int = 5
) -> str:
    """Build the prompt string for helix-builder.

    Args:
        task_data: Dict with keys from TaskGet result:
            - subject: Task title (e.g., "001: impl-auth")
            - description: Task objective
            - metadata: {delta, verify, budget, framework, idioms}
        lineage: List of {seq, slug, delivered} from parent tasks
        memory_limit: Max memories to inject

    Returns:
        Formatted prompt string for builder agent
    """
    lineage = lineage or []
    metadata = task_data.get("metadata", {})
    objective = task_data.get("description", "")

    # Query memory for relevant context
    memories = _query_memory(objective, limit=memory_limit)
    failures = [m for m in memories if m.get("type") == "failure"]
    patterns = [m for m in memories if m.get("type") == "pattern"]
    injected = [m["name"] for m in memories]

    # Format failures and patterns for builder
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
DELTA: {json.dumps(metadata.get("delta", []))}
VERIFY: {metadata.get("verify", "")}
BUDGET: {metadata.get("budget", 7)}
FRAMEWORK: {metadata.get("framework") or "none"}
IDIOMS: {json.dumps(metadata.get("idioms", {}))}
FAILURES_TO_AVOID: {json.dumps(failure_hints)}
PATTERNS_TO_APPLY: {json.dumps(pattern_hints)}
INJECTED_MEMORIES: {json.dumps(injected)}
PARENT_DELIVERIES: {json.dumps(lineage)}

Execute this task following your builder protocol. Report DELIVERED or BLOCKED with UTILIZED list."""

    return prompt


def get_injected_memories(objective: str, limit: int = 5) -> List[str]:
    """Get list of memory names that were injected for feedback tracking.

    Called after builder completes to know which memories were offered.

    Args:
        objective: The task objective used for memory query
        limit: Max memories (must match what was used in build_prompt)

    Returns:
        List of memory names that were injected
    """
    memories = _query_memory(objective, limit=limit)
    return [m["name"] for m in memories]


def _query_memory(objective: str, limit: int = 5) -> List[dict]:
    """Query memory system for relevant memories.

    Direct call to memory layer - no subprocess overhead.
    """
    try:
        return recall(objective, limit=limit)
    except Exception:
        return []


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


# CLI for orchestrator usage
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Build execution context for builders")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build-prompt
    p = subparsers.add_parser("build-prompt", help="Build prompt from task data")
    p.add_argument("--task-data", required=True, help="JSON task data from TaskGet")
    p.add_argument("--lineage", default="[]", help="JSON lineage from parent tasks")
    p.add_argument("--memory-limit", type=int, default=5)

    # get-injected
    p = subparsers.add_parser("get-injected", help="Get memory names that were injected")
    p.add_argument("--objective", required=True, help="Task objective")
    p.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()

    if args.command == "build-prompt":
        task_data = json.loads(args.task_data)
        lineage = json.loads(args.lineage)
        prompt = build_prompt(task_data, lineage, args.memory_limit)
        print(prompt)
    elif args.command == "get-injected":
        names = get_injected_memories(args.objective, args.limit)
        print(json.dumps(names))


if __name__ == "__main__":
    _cli()
