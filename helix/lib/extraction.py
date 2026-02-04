"""Insight extraction from agent transcripts.

Single extraction function replaces 6 agent-specific extractors.
"""

import json
import re
from typing import Optional


def extract_insight(transcript: str) -> Optional[dict]:
    """Extract insight from any agent transcript.

    Looks for: INSIGHT: {"content": "When X, do Y because Z"}
    Fallback: Derives from DELIVERED/BLOCKED outcome

    Returns: {"content": str, "tags": list} or None
    """
    # Primary: explicit INSIGHT line
    match = re.search(r'INSIGHT:\s*(\{[^}]+\})', transcript, re.IGNORECASE)
    if match:
        try:
            data = json.loads(match.group(1))
            content = data.get("content", "").strip()
            if content and len(content) >= 20:
                return {
                    "content": content,
                    "tags": data.get("tags", [])
                }
        except json.JSONDecodeError:
            pass

    # Fallback: derive from DELIVERED/BLOCKED with context
    delivered = re.search(r'DELIVERED:\s*(.+?)(?:\n|$)', transcript, re.IGNORECASE)
    blocked = re.search(r'BLOCKED:\s*(.+?)(?:\n|$)', transcript, re.IGNORECASE)

    if delivered:
        summary = delivered.group(1).strip()
        # Look for task context
        task_match = re.search(r'(?:TASK|OBJECTIVE):\s*(.+?)(?:\n|$)', transcript, re.IGNORECASE)
        task = task_match.group(1).strip() if task_match else ""
        if task and summary:
            return {
                "content": f"For '{task[:100]}': {summary[:200]}",
                "tags": ["derived", "success"]
            }

    if blocked:
        reason = blocked.group(1).strip()
        task_match = re.search(r'(?:TASK|OBJECTIVE):\s*(.+?)(?:\n|$)', transcript, re.IGNORECASE)
        task = task_match.group(1).strip() if task_match else ""
        if reason:
            content = f"When attempting '{task[:100]}': blocked by {reason[:200]}" if task else f"Blocked: {reason[:250]}"
            return {
                "content": content,
                "tags": ["derived", "failure"]
            }

    return None


def extract_outcome(transcript: str) -> str:
    """Extract outcome from transcript.

    Returns: "delivered"|"blocked"|"unknown"
    """
    if re.search(r'DELIVERED:', transcript, re.IGNORECASE):
        return "delivered"
    if re.search(r'BLOCKED:', transcript, re.IGNORECASE):
        return "blocked"
    return "unknown"


def extract_injected_names(transcript: str) -> list:
    """Extract injected insight names from transcript.

    Looks for: INJECTED: ["name1", "name2"]
    """
    match = re.search(r'INJECTED:\s*(\[[^\]]*\])', transcript, re.IGNORECASE)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return []


def process_completion(transcript: str, agent_type: str = "builder") -> dict:
    """Process agent completion for learning.

    Called by SubagentStop hook.

    Returns: {
        "insight": {...} | None,
        "outcome": "delivered"|"blocked"|"unknown",
        "injected": ["name1", "name2"]
    }
    """
    return {
        "insight": extract_insight(transcript),
        "outcome": extract_outcome(transcript),
        "injected": extract_injected_names(transcript)
    }
