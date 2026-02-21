"""Insight injection for agents.

Single injection function replaces 4-query context builder.
Shared formatting used by both orchestrator (batch_inject) and hook (inject_memory).
CLI entry point: python3 injection.py batch-inject --tasks '["obj1","obj2"]' --limit 3
"""

import json
import sys
from typing import Optional, List, Tuple

# Cold-start signal when no insights exist at all
NO_PRIOR_MEMORY = "NO_PRIOR_MEMORY: Novel domain."

# Signal when insights exist but none matched this task
NO_MATCHING_MEMORY = "NO_MATCHING_INSIGHTS: No matching insights found for this task."

# Shared header for insight injection — used in format_prompt(), inject_memory hook, and transcript detection
INSIGHTS_HEADER = "INSIGHTS (from past experience):"

# Session-level diversity tracking
_session_injected: set = set()


def reset_session_tracking():
    """Reset session injection tracking."""
    global _session_injected
    _session_injected = set()


def format_insights(memories: list) -> Tuple[List[str], List[str]]:
    """Format recalled insights into display lines and name list.

    Shared between orchestrator injection (inject_context/format_prompt)
    and hook injection (inject_memory._format_additional_context).

    Args:
        memories: List of insight dicts from recall()

    Returns: (lines, names) where lines are "[XX%] content" strings
             and names are insight name strings for INJECTED attribution
    """
    lines = []
    names = []
    for m in memories:
        eff = m.get("_effectiveness", m.get("effectiveness", 0.5))
        eff_pct = int(eff * 100)
        content = m.get("content", "")
        if content:
            lines.append(f"[{eff_pct}%] {content}")
            name = m.get("name", "")
            if name:
                names.append(name)
    return lines, names


def inject_context(objective: str, limit: int = 3,
                    min_relevance: Optional[float] = None,
                    diversify: bool = True) -> dict:
    """Build memory context for any agent.

    Args:
        objective: Task objective for semantic search
        limit: Maximum insights to inject
        min_relevance: Optional override for minimum cosine similarity threshold

    Returns: {
        "insights": ["[75%] When X, do Y", ...],
        "names": ["insight-name-1", ...]
    }
    """
    global _session_injected

    # Import here to avoid circular dependency
    from lib.memory.core import recall

    kwargs = {"limit": limit}
    if min_relevance is not None:
        kwargs["min_relevance"] = min_relevance
    if diversify and _session_injected:
        kwargs["suppress_names"] = list(_session_injected)
    memories = recall(objective, **kwargs)
    insights, names = format_insights(memories)

    if diversify:
        _session_injected.update(names)

    result = {
        "insights": insights,
        "names": names
    }

    # When recall returns empty, distinguish "no insights exist" from "none matched"
    if not memories:
        from lib.memory.core import count
        result["total_insights"] = count()

    return result


def format_prompt(
    task_id: str,
    task: str,
    objective: str,
    verify: str,
    insights: list,
    injected_names: list,
    warning: str = "",
    parent_deliveries: str = "",
    relevant_files: Optional[List[str]] = None,
    total_insights: int = 0
) -> str:
    """Format complete builder prompt.

    Returns prompt with fields:
    - TASK_ID
    - TASK
    - OBJECTIVE
    - VERIFY
    - RELEVANT_FILES (file paths relevant to the task, if any)
    - WARNING (cross-wave convergent issues, if any)
    - PARENT_DELIVERIES (completed blocker summaries, if any)
    - INSIGHTS (if any), NO_MATCHING_INSIGHTS, or NO_PRIOR_MEMORY cold-start signal
    - INJECTED (names for feedback loop)
    """
    lines = [
        f"TASK_ID: {task_id}",
        f"TASK: {task}",
        f"OBJECTIVE: {objective}",
        f"VERIFY: {verify}",
    ]

    if relevant_files:
        lines.append(f"RELEVANT_FILES: {', '.join(relevant_files)}")

    if warning:
        lines.append("")
        lines.append(f"WARNING: {warning}")

    if parent_deliveries:
        lines.append("")
        lines.append("PARENT_DELIVERIES:")
        lines.append(parent_deliveries)

    if insights:
        lines.append("")
        lines.append(INSIGHTS_HEADER)
        for insight in insights:
            lines.append(f"  - {insight}")
    else:
        lines.append("")
        if total_insights > 0:
            lines.append(NO_MATCHING_MEMORY)
        else:
            lines.append(NO_PRIOR_MEMORY)

    if injected_names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(injected_names)}")

    return "\n".join(lines)


def batch_inject(tasks: List[str], limit: int = 3) -> dict:
    """Inject context for multiple tasks with cross-task diversity.

    Session diversity is automatically applied: insights injected for
    earlier tasks are suppressed in later ones.

    Args:
        tasks: List of task objectives
        limit: Maximum insights per task

    Returns: {"results": [inject_context result, ...], "total_unique": int}
    """
    results = []
    all_names = set()

    for objective in tasks:
        ctx = inject_context(objective, limit=limit, diversify=True)
        results.append(ctx)
        all_names.update(ctx["names"])

    return {
        "results": results,
        "total_unique": len(all_names)
    }


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import argparse
    from pathlib import Path

    # Support both module and script execution
    sys.path.insert(0, str(Path(__file__).parent))

    p = argparse.ArgumentParser(description="Helix insight injection")
    p.add_argument("--db", help="Override database path")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("batch-inject", help="Inject context for multiple tasks with cross-task diversity")
    s.add_argument("--tasks", required=True, help="JSON array of task objectives")
    s.add_argument("--limit", type=int, default=3, help="Max insights per task")

    s = sub.add_parser("inject", help="Inject context for a single task")
    s.add_argument("objective", help="Task objective for semantic search")
    s.add_argument("--limit", type=int, default=3)

    args = p.parse_args()

    if args.db:
        import os
        import db.connection as conn_module
        resolved = str(Path(args.db).resolve())
        os.environ["HELIX_DB_PATH"] = resolved
        conn_module.DB_PATH = resolved
        conn_module.reset_db()

    if args.cmd == "batch-inject":
        reset_session_tracking()
        tasks = json.loads(args.tasks)
        print(json.dumps(batch_inject(tasks, args.limit)))
    elif args.cmd == "inject":
        reset_session_tracking()
        print(json.dumps(inject_context(args.objective, limit=args.limit)))
