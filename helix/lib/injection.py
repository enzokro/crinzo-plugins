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

# Strategic recall — orchestrator RECALL phase (broader than tactical limit=3)
STRATEGIC_RECALL_LIMIT = 15
STRATEGIC_MIN_RELEVANCE = 0.30       # Wider gate than tactical (0.35); still above noise floor (0.05-0.25)
STRATEGIC_HIGH_EFFECTIVENESS = 0.70  # "Proven" — classify for CONSTRAINTS
STRATEGIC_LOW_EFFECTIVENESS = 0.40   # "Risky" — classify for RISK_AREAS


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


def strategic_recall(objective: str,
                     limit: int = STRATEGIC_RECALL_LIMIT,
                     min_relevance: float = STRATEGIC_MIN_RELEVANCE) -> dict:
    """Broad recall with summary statistics for orchestrator RECALL phase.

    Unlike inject_context() (tactical, limit=3, formatted for builders),
    this returns raw insight dicts with tags and pre-computed summary stats
    for orchestrator-level synthesis into CONSTRAINTS, RISK_AREAS, and
    EXPLORATION_TARGETS.

    Args:
        objective: Objective for semantic search
        limit: Maximum insights (default 15, broader than tactical)
        min_relevance: Minimum cosine similarity (default 0.30, wider gate)

    Returns: {
        "insights": [{name, content, effectiveness, use_count, causal_hits,
                      tags, _relevance, _effectiveness, _score}, ...],
        "summary": {total_recalled, total_in_system, avg_relevance,
                    avg_effectiveness, proven_count, risky_count,
                    untested_count, tag_distribution, coverage_ratio}
    }
    """
    from lib.memory.core import recall, count

    total_in_system = count()
    memories = recall(objective, limit=limit, min_relevance=min_relevance)

    # Batch-fetch tags for recalled insights
    if memories:
        try:
            from lib.db.connection import get_db
        except ImportError:
            from db.connection import get_db

        names = [m["name"] for m in memories]
        placeholders = ",".join("?" for _ in names)
        db = get_db()
        tag_rows = db.execute(
            f"SELECT name, tags FROM insight WHERE name IN ({placeholders})",
            names
        ).fetchall()
        tags_by_name = {}
        for r in tag_rows:
            if r["tags"]:
                try:
                    tags_by_name[r["name"]] = json.loads(r["tags"])
                except Exception:
                    tags_by_name[r["name"]] = []
            else:
                tags_by_name[r["name"]] = []

        # Enrich insights with tags
        for m in memories:
            m["tags"] = tags_by_name.get(m["name"], [])

    # Compute summary statistics
    total_recalled = len(memories)
    avg_relevance = 0.0
    avg_effectiveness = 0.0
    proven_count = 0
    risky_count = 0
    untested_count = 0
    tag_distribution: dict = {}

    if memories:
        relevances = [m.get("_relevance", 0.0) for m in memories]
        effectivenesses = [m.get("_effectiveness", m.get("effectiveness", 0.5)) for m in memories]
        avg_relevance = round(sum(relevances) / len(relevances), 3)
        avg_effectiveness = round(sum(effectivenesses) / len(effectivenesses), 3)

        for m in memories:
            eff = m.get("_effectiveness", m.get("effectiveness", 0.5))
            use_count = m.get("use_count", 0)

            if eff >= STRATEGIC_HIGH_EFFECTIVENESS:
                proven_count += 1
            elif eff < STRATEGIC_LOW_EFFECTIVENESS:
                risky_count += 1

            if use_count < 3:
                untested_count += 1

            for tag in m.get("tags", []):
                tag_distribution[tag] = tag_distribution.get(tag, 0) + 1

    coverage_ratio = round(total_recalled / total_in_system, 3) if total_in_system > 0 else 0.0

    return {
        "insights": memories,
        "summary": {
            "total_recalled": total_recalled,
            "total_in_system": total_in_system,
            "avg_relevance": avg_relevance,
            "avg_effectiveness": avg_effectiveness,
            "proven_count": proven_count,
            "risky_count": risky_count,
            "untested_count": untested_count,
            "tag_distribution": tag_distribution,
            "coverage_ratio": coverage_ratio,
        }
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

    s = sub.add_parser("strategic-recall", help="Broad recall with summary for orchestrator RECALL phase")
    s.add_argument("objective", help="Objective for semantic search")
    s.add_argument("--limit", type=int, default=STRATEGIC_RECALL_LIMIT)
    s.add_argument("--min-relevance", type=float, default=STRATEGIC_MIN_RELEVANCE)

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
    elif args.cmd == "strategic-recall":
        print(json.dumps(strategic_recall(args.objective, limit=args.limit,
                                          min_relevance=args.min_relevance), indent=2))
