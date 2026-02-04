"""Insight injection for agents.

Single injection function replaces 4-query context builder.
"""

import json
from typing import Optional


def inject_context(objective: str, limit: int = 5) -> dict:
    """Build memory context for any agent.

    Args:
        objective: Task objective for semantic search
        limit: Maximum insights to inject

    Returns: {
        "insights": ["[75%] When X, do Y", ...],
        "names": ["insight-name-1", ...]
    }
    """
    # Import here to avoid circular dependency
    from lib.memory.core import recall

    memories = recall(objective, limit=limit)

    insights = []
    names = []

    for m in memories:
        eff_pct = int(m.get("effectiveness", 0.5) * 100)
        content = m.get("content", "")
        if content:
            insights.append(f"[{eff_pct}%] {content}")
            names.append(m.get("name", ""))

    return {
        "insights": insights,
        "names": [n for n in names if n]
    }


def format_prompt(
    task_id: str,
    task: str,
    objective: str,
    verify: str,
    insights: list,
    injected_names: list
) -> str:
    """Format complete builder prompt.

    Returns prompt with fields:
    - TASK_ID
    - TASK
    - OBJECTIVE
    - VERIFY
    - INSIGHTS (if any)
    - INJECTED (names for feedback loop)
    """
    lines = [
        f"TASK_ID: {task_id}",
        f"TASK: {task}",
        f"OBJECTIVE: {objective}",
        f"VERIFY: {verify}",
    ]

    if insights:
        lines.append("")
        lines.append("INSIGHTS (from past experience):")
        for insight in insights:
            lines.append(f"  - {insight}")

    if injected_names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(injected_names)}")

    return "\n".join(lines)


def build_agent_prompt(task_data: dict) -> str:
    """Build complete prompt for builder agent.

    Args:
        task_data: Dict with task_id, task, objective, verify

    Returns: Formatted prompt string
    """
    task_id = task_data.get("task_id", "")
    task = task_data.get("task", "")
    objective = task_data.get("objective", task)
    verify = task_data.get("verify", "")

    # Get relevant insights
    context = inject_context(objective, limit=5)

    return format_prompt(
        task_id=task_id,
        task=task,
        objective=objective,
        verify=verify,
        insights=context["insights"],
        injected_names=context["names"]
    )
