"""Insight extraction from agent transcripts.

Single extraction function replaces 6 agent-specific extractors.
"""

import json
import re
from typing import Optional


def _extract_json_after(text: str, marker: str) -> Optional[dict]:
    """Extract first JSON object after marker using balanced brace matching."""
    idx = text.lower().find(marker.lower())
    if idx < 0:
        return None
    start = text.find('{', idx)
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        if depth == 0:
            try:
                return json.loads(text[start:i + 1])
            except json.JSONDecodeError:
                return None
    return None


def extract_insight(transcript: str) -> Optional[dict]:
    """Extract insight from any agent transcript.

    Looks for: INSIGHT: {"content": "When X, do Y because Z"}
    Fallback: Derives from BLOCKED outcome only

    Returns: {"content": str, "tags": list} or None
    """
    # Primary: explicit INSIGHT line (balanced brace extraction)
    data = _extract_json_after(transcript, 'INSIGHT:')
    if data:
        content = data.get("content", "").strip()
        if content and len(content) >= 20:
            return {
                "content": content,
                "tags": data.get("tags", [])
            }

    # Fallback ONLY for failures
    blocked_matches = re.findall(r'BLOCKED:\s*(.+)', transcript, re.IGNORECASE)
    if blocked_matches:
        reason = blocked_matches[-1].strip()
        task_matches = re.findall(r'(?:TASK|OBJECTIVE):\s*(.+)', transcript, re.IGNORECASE)
        task = task_matches[-1].strip() if task_matches else ""
        if reason:
            content = f"When attempting '{task[:100]}': blocked by {reason[:200]}" if task else f"Blocked: {reason[:250]}"
            return {
                "content": content,
                "tags": ["derived", "failure"]
            }

    return None


def extract_outcome(transcript: str) -> str:
    """Extract outcome from transcript.

    Returns: "delivered"|"blocked"|"plan_complete"|"unknown"
    """
    if re.search(r'DELIVERED:', transcript, re.IGNORECASE):
        return "delivered"
    if re.search(r'BLOCKED:', transcript, re.IGNORECASE):
        return "blocked"
    if re.search(r'PLAN_COMPLETE:', transcript, re.IGNORECASE):
        return "plan_complete"
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


def process_completion(transcript: str) -> dict:
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
