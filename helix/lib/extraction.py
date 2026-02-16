"""Insight extraction from agent transcripts.

Single extraction function replaces 6 agent-specific extractors.
"""

import json
import re
from typing import Optional

# Pre-compiled patterns for single-pass marker extraction
_OUTCOME_RE = re.compile(r'(DELIVERED|BLOCKED|PARTIAL|PLAN_COMPLETE|REMAINING):\s*(.+)', re.IGNORECASE)
_TASK_RE = re.compile(r'(?:TASK|OBJECTIVE):\s*(.+)', re.IGNORECASE)
_INJECTED_RE = re.compile(r'INJECTED:\s*(\[[^\]]*\])', re.IGNORECASE)


def _extract_json_after(text: str, marker: str) -> Optional[dict]:
    """Extract first JSON object after marker using json.raw_decode."""
    m = re.search(re.escape(marker), text, re.IGNORECASE)
    if m is None:
        return None
    idx = m.start()
    start = text.find('{', idx)
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text, start)
        return obj if isinstance(obj, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


def extract_insight(transcript: str, outcome: str = None,
                     summary_parts: list = None,
                     task_parts: list = None) -> Optional[dict]:
    """Extract insight from any agent transcript.

    Looks for: INSIGHT: {"content": "When X, do Y because Z"}
    Fallback: Derives from BLOCKED outcome only

    Args:
        transcript: Full transcript text (needed for INSIGHT: JSON extraction)
        outcome: Pre-determined outcome — skips BLOCKED re-scan when provided
        summary_parts: Pre-extracted DELIVERED/BLOCKED summaries (avoids re-scanning)
        task_parts: Pre-extracted TASK/OBJECTIVE parts (avoids re-scanning)

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

    # Fallback ONLY for failures — derive insight from BLOCKED/PARTIAL reason
    # When called from process_completion, use pre-extracted parts to avoid re-scanning
    if outcome is not None:
        is_blocked = outcome in ("blocked", "partial")
    else:
        is_blocked = bool(re.search(r'(?:BLOCKED|PARTIAL):', transcript, re.IGNORECASE))

    if not is_blocked:
        return None

    if summary_parts is not None:
        reason = summary_parts[-1].strip() if summary_parts else ""
    else:
        blocked_matches = re.findall(r'(?:BLOCKED|PARTIAL|REMAINING):\s*(.+)', transcript, re.IGNORECASE)
        reason = blocked_matches[-1].strip() if blocked_matches else ""

    if not reason:
        return None

    if task_parts is not None:
        task = task_parts[-1].strip() if task_parts else ""
    else:
        task_matches = re.findall(r'(?:TASK|OBJECTIVE):\s*(.+)', transcript, re.IGNORECASE)
        task = task_matches[-1].strip() if task_matches else ""

    content = f"When {task[:100]}, be aware that {reason[:200]} can block progress" if task else f"Be aware that {reason[:250]} can block progress"
    return {
        "content": content,
        "tags": ["derived", "failure"],
        "derived": True
    }


def extract_outcome(transcript: str) -> str:
    """Extract outcome from transcript. Last match wins.

    Returns: "delivered"|"blocked"|"partial"|"plan_complete"|"unknown"
    """
    outcome = "unknown"
    for m in _OUTCOME_RE.finditer(transcript):
        marker = m.group(1).upper()
        if marker == "DELIVERED":
            outcome = "delivered"
        elif marker == "BLOCKED":
            outcome = "blocked"
        elif marker == "PARTIAL":
            outcome = "partial"
        elif marker == "PLAN_COMPLETE":
            outcome = "plan_complete"
    return outcome


def extract_summary_parts(transcript: str) -> list:
    """Extract DELIVERED/BLOCKED/PARTIAL summary text from transcript.

    Returns list of matched text after DELIVERED:, BLOCKED:, or PARTIAL: markers.
    """
    return re.findall(r'(?:DELIVERED|BLOCKED|PARTIAL):\s*(.+)', transcript, re.IGNORECASE)


def extract_task_parts(transcript: str) -> list:
    """Extract TASK/OBJECTIVE text from transcript.

    Returns list of matched text after TASK: or OBJECTIVE: markers.
    """
    return re.findall(r'(?:TASK|OBJECTIVE):\s*(.+)', transcript, re.IGNORECASE)


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

    Called by SubagentStop hook. Single-pass marker scan feeds all extractors.

    Returns: {
        "insight": {...} | None,
        "outcome": "delivered"|"blocked"|"partial"|"plan_complete"|"unknown",
        "injected": ["name1", "name2"],
        "summary_parts": ["summary text after DELIVERED/BLOCKED markers"],
        "task_parts": ["text after TASK/OBJECTIVE markers"]
    }
    """
    # Single-pass: scan all markers at once
    outcome = "unknown"
    summary_parts = []
    task_parts = []
    injected = []

    for m in _OUTCOME_RE.finditer(transcript):
        marker = m.group(1).upper()
        text = m.group(2).strip()
        # Last-match-wins: agent's actual output is at end of transcript.
        # Earlier matches may be from injected context or PARENT_DELIVERIES.
        if marker == "DELIVERED":
            outcome = "delivered"
        elif marker == "BLOCKED":
            outcome = "blocked"
        elif marker == "PARTIAL":
            outcome = "partial"
        elif marker == "PLAN_COMPLETE":
            outcome = "plan_complete"
        summary_parts.append(text)

    for m in _TASK_RE.finditer(transcript):
        task_parts.append(m.group(1).strip())

    m = _INJECTED_RE.search(transcript)
    if m:
        try:
            injected = json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Insight extraction: pass pre-extracted parts to avoid redundant regex scans
    insight = extract_insight(transcript, outcome=outcome,
                               summary_parts=summary_parts, task_parts=task_parts)

    return {
        "insight": insight,
        "outcome": outcome,
        "injected": injected,
        "summary_parts": summary_parts,
        "task_parts": task_parts,
    }
