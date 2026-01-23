"""Metacognition module for approach assessment.

Provides meta-level reasoning about task approaches:
- Detect stuck loops (same approach failing repeatedly)
- Suggest pivots based on memory patterns
- Track attempt history within session
"""

from typing import List, Dict, Optional
from datetime import datetime

# Session-level tracking (not persisted)
_attempt_history: Dict[str, List[dict]] = {}


def assess_approach(
    task_objective: str,
    current_approach: str,
    memories: Optional[List[dict]] = None
) -> dict:
    """Assess whether to continue with current approach or pivot.

    Args:
        task_objective: What we're trying to accomplish
        current_approach: How we're trying to do it
        memories: Relevant memories from recall()

    Returns:
        {
            "recommendation": "continue" | "pivot" | "escalate",
            "reason": str,
            "attempts": int,
            "suggested_pivot": str | None
        }
    """
    memories = memories or []

    # Track this attempt
    key = task_objective[:100]
    if key not in _attempt_history:
        _attempt_history[key] = []

    _attempt_history[key].append({
        "approach": current_approach,
        "timestamp": datetime.now().isoformat()
    })

    attempts = _attempt_history[key]
    attempt_count = len(attempts)

    # Check for repeated same approach
    if attempt_count >= 3:
        recent_approaches = [a["approach"][:50] for a in attempts[-3:]]
        if len(set(recent_approaches)) == 1:
            # Same approach 3 times - PIVOT
            pivot_suggestion = _suggest_pivot(task_objective, current_approach, memories)
            return {
                "recommendation": "pivot",
                "reason": f"Same approach attempted {attempt_count} times without success",
                "attempts": attempt_count,
                "suggested_pivot": pivot_suggestion
            }

    # Check if approaching escalation threshold
    if attempt_count >= 5:
        return {
            "recommendation": "escalate",
            "reason": f"{attempt_count} attempts - consider escalating to user",
            "attempts": attempt_count,
            "suggested_pivot": None
        }

    # Check memories for failure patterns
    failure_patterns = [m for m in memories if m.get("type") == "failure"]
    matching_failures = []
    for f in failure_patterns:
        trigger = f.get("trigger", "").lower()
        if any(word in trigger for word in current_approach.lower().split()[:5]):
            matching_failures.append(f)

    if matching_failures:
        # We have memory of this approach failing before
        best_failure = max(matching_failures, key=lambda x: x.get("effectiveness", 0))
        return {
            "recommendation": "pivot",
            "reason": f"Memory suggests this approach fails: {best_failure.get('trigger', '')[:60]}",
            "attempts": attempt_count,
            "suggested_pivot": best_failure.get("resolution", "")[:200]
        }

    return {
        "recommendation": "continue",
        "reason": "No concerning patterns detected",
        "attempts": attempt_count,
        "suggested_pivot": None
    }


def _suggest_pivot(
    task_objective: str,
    current_approach: str,
    memories: List[dict]
) -> Optional[str]:
    """Suggest an alternative approach based on patterns."""
    # Look for successful patterns
    patterns = [m for m in memories if m.get("type") == "pattern"]
    if patterns:
        best = max(patterns, key=lambda x: x.get("effectiveness", 0))
        return best.get("resolution", "")[:200]

    # Look for failure resolutions that suggest alternatives
    failures = [m for m in memories if m.get("type") == "failure"]
    for f in failures:
        resolution = f.get("resolution", "")
        if "instead" in resolution.lower() or "try" in resolution.lower():
            return resolution[:200]

    return "Try a fundamentally different approach"


def clear_history(task_objective: Optional[str] = None) -> dict:
    """Clear attempt history.

    Args:
        task_objective: Clear specific task, or all if None
    """
    global _attempt_history

    if task_objective:
        key = task_objective[:100]
        if key in _attempt_history:
            del _attempt_history[key]
            return {"cleared": key}
        return {"cleared": None}

    count = len(_attempt_history)
    _attempt_history = {}
    return {"cleared_all": count}


def get_history(task_objective: Optional[str] = None) -> dict:
    """Get attempt history for debugging."""
    if task_objective:
        key = task_objective[:100]
        return {
            "task": key,
            "attempts": _attempt_history.get(key, [])
        }

    return {
        "tasks": list(_attempt_history.keys()),
        "total_attempts": sum(len(v) for v in _attempt_history.values())
    }
