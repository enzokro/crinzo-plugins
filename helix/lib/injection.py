"""Insight injection for agents.

Single injection function replaces 4-query context builder.
"""

import json
from datetime import datetime, timezone
from typing import Optional, List

from lib.paths import get_helix_dir

# Session-level diversity tracking
_session_injected: set = set()


def reset_session_tracking():
    """Reset session injection tracking."""
    global _session_injected
    _session_injected = set()


def inject_context(objective: str, limit: int = 5, task_id: Optional[str] = None,
                    min_relevance: Optional[float] = None,
                    diversify: bool = True) -> dict:
    """Build memory context for any agent.

    Args:
        objective: Task objective for semantic search
        limit: Maximum insights to inject
        task_id: Optional task ID; if provided, writes injection state for audit
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

    insights = []
    names = []

    for m in memories:
        # Prefer causal-adjusted effectiveness (from recall scoring) over raw
        eff = m.get("_effectiveness", m.get("effectiveness", 0.5))
        eff_pct = int(eff * 100)
        content = m.get("content", "")
        if content:
            insights.append(f"[{eff_pct}%] {content}")
            names.append(m.get("name", ""))

    names = [n for n in names if n]

    if diversify:
        _session_injected.update(names)

    # Write injection state for audit trail (foreground agents don't trigger SubagentStop)
    if task_id:
        state_dir = get_helix_dir() / "injection-state"
        state_dir.mkdir(parents=True, exist_ok=True)
        state_file = state_dir / f"{task_id}.json"
        state_file.write_text(json.dumps({
            "task_id": task_id,
            "query": objective,
            "names": names,
            "ts": datetime.now(timezone.utc).isoformat()
        }))

    return {
        "insights": insights,
        "names": names
    }


def format_prompt(
    task_id: str,
    task: str,
    objective: str,
    verify: str,
    insights: list,
    injected_names: list,
    warning: str = "",
    parent_deliveries: str = ""
) -> str:
    """Format complete builder prompt.

    Returns prompt with fields:
    - TASK_ID
    - TASK
    - OBJECTIVE
    - VERIFY
    - WARNING (cross-wave convergent issues, if any)
    - PARENT_DELIVERIES (completed blocker summaries, if any)
    - INSIGHTS (if any) or NO_PRIOR_MEMORY cold-start signal
    - INJECTED (names for feedback loop)
    """
    lines = [
        f"TASK_ID: {task_id}",
        f"TASK: {task}",
        f"OBJECTIVE: {objective}",
        f"VERIFY: {verify}",
    ]

    if warning:
        lines.append("")
        lines.append(f"WARNING: {warning}")

    if parent_deliveries:
        lines.append("")
        lines.append("PARENT_DELIVERIES:")
        lines.append(parent_deliveries)

    if insights:
        lines.append("")
        lines.append("INSIGHTS (from past experience):")
        for insight in insights:
            lines.append(f"  - {insight}")
    else:
        # Cold-start signal: encourage richer extraction from novel domains
        lines.append("")
        lines.append("NO_PRIOR_MEMORY: Novel domain. Your INSIGHT output is especially valuable.")

    if injected_names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(injected_names)}")

    return "\n".join(lines)


def batch_inject(tasks: List[str], limit: int = 5,
                 task_ids: List[str] = None) -> dict:
    """Inject context for multiple tasks with cross-task diversity.

    Session diversity is automatically applied: insights injected for
    earlier tasks are suppressed in later ones.

    Args:
        tasks: List of task objectives
        limit: Maximum insights per task
        task_ids: Optional list of task IDs (same length as tasks).
                  When provided, writes injection-state files for audit trail.

    Returns: {"results": [inject_context result, ...], "total_unique": int}
    """
    results = []
    all_names = set()

    for i, objective in enumerate(tasks):
        tid = task_ids[i] if task_ids and i < len(task_ids) else None
        ctx = inject_context(objective, limit=limit, task_id=tid, diversify=True)
        results.append(ctx)
        all_names.update(ctx["names"])

    return {
        "results": results,
        "total_unique": len(all_names)
    }
