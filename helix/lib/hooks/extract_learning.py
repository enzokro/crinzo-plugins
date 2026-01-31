#!/usr/bin/env python3
"""Learning extraction from helix agent transcripts.

Called by SubagentStop hook. Parses agent transcripts for completion
markers and extracts learning candidates for orchestrator review.

Extraction patterns by agent type:

Builder:
    - Look for `learned` field in output
    - Extract pattern/failure/convention candidates

Explorer:
    - Look for FINDINGS section
    - Extract fact candidates

Planner:
    - Look for LEARNED block
    - Extract decision/evolution candidates

Output written to .helix/learning-queue/{agent_id}.json
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def get_helix_dir() -> Path:
    """Get .helix directory, creating if needed."""
    helix_dir = Path.cwd() / ".helix"
    helix_dir.mkdir(exist_ok=True)
    return helix_dir


def get_learning_queue_dir() -> Path:
    """Get learning queue directory."""
    queue_dir = get_helix_dir() / "learning-queue"
    queue_dir.mkdir(exist_ok=True)
    return queue_dir


def get_injection_state(tool_use_id: str) -> Optional[dict]:
    """Load injection state for an agent invocation.

    Args:
        tool_use_id: Tool use ID from agent spawn

    Returns:
        Injection state dict or None
    """
    state_dir = get_helix_dir() / "injection-state"
    state_file = state_dir / f"{tool_use_id}.json"

    if state_file.exists():
        try:
            return json.loads(state_file.read_text())
        except json.JSONDecodeError:
            return None
    return None


def extract_learned_field(transcript: str) -> Optional[dict]:
    """Extract `learned` JSON field from builder output.

    Builders may output:
        learned: {"trigger": "...", "resolution": "...", "type": "pattern"}

    Args:
        transcript: Full agent transcript

    Returns:
        Parsed learned dict or None
    """
    # Look for learned: followed by JSON
    patterns = [
        r'learned:\s*(\{[^}]+\})',
        r'"learned":\s*(\{[^}]+\})',
        r'`learned`:\s*(\{[^}]+\})',
    ]

    for pattern in patterns:
        match = re.search(pattern, transcript, re.IGNORECASE | re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None


def extract_outcome(transcript: str) -> str:
    """Extract outcome from builder transcript.

    Builders report DELIVERED or BLOCKED.

    Args:
        transcript: Full agent transcript

    Returns:
        "delivered", "blocked", or "unknown"
    """
    # Look for outcome indicators
    if re.search(r'\bDELIVERED\b', transcript, re.IGNORECASE):
        return "delivered"
    if re.search(r'\bBLOCKED\b', transcript, re.IGNORECASE):
        return "blocked"
    return "unknown"


def extract_findings_section(transcript: str) -> List[str]:
    """Extract FINDINGS section from explorer transcript.

    Explorers output:
        ## FINDINGS
        - Finding 1
        - Finding 2

    Args:
        transcript: Full agent transcript

    Returns:
        List of finding strings
    """
    findings = []

    # Look for FINDINGS section
    match = re.search(
        r'(?:##\s*)?FINDINGS?\s*[\n:](.+?)(?=(?:##|$))',
        transcript,
        re.IGNORECASE | re.DOTALL
    )

    if match:
        section = match.group(1)
        # Extract bullet points
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith(('-', '*', '•')):
                findings.append(line.lstrip('-*• ').strip())

    return findings


def extract_learned_block(transcript: str) -> List[str]:
    """Extract LEARNED block from planner transcript.

    Planners may output:
        ### LEARNED
        - Decision: We chose X because Y
        - Pattern: When doing Z, always W

    Args:
        transcript: Full agent transcript

    Returns:
        List of learned strings
    """
    learned = []

    # Look for LEARNED section
    match = re.search(
        r'(?:###?\s*)?LEARNED\s*[\n:](.+?)(?=(?:###?|$))',
        transcript,
        re.IGNORECASE | re.DOTALL
    )

    if match:
        section = match.group(1)
        for line in section.split('\n'):
            line = line.strip()
            if line.startswith(('-', '*', '•')):
                learned.append(line.lstrip('-*• ').strip())

    return learned


def classify_learning(text: str) -> str:
    """Classify a learning candidate by type.

    Args:
        text: Learning text

    Returns:
        "pattern", "failure", "convention", "decision", "fact", "evolution"
    """
    text_lower = text.lower()

    # Check for explicit type prefixes
    if text_lower.startswith("decision:"):
        return "decision"
    if text_lower.startswith("pattern:"):
        return "pattern"
    if text_lower.startswith("convention:"):
        return "convention"
    if text_lower.startswith("fact:"):
        return "fact"

    # Heuristics
    if any(w in text_lower for w in ["always", "never", "should", "must"]):
        return "convention"
    if any(w in text_lower for w in ["failed", "error", "broke", "doesn't work"]):
        return "failure"
    if any(w in text_lower for w in ["decided", "chose", "because"]):
        return "decision"
    if any(w in text_lower for w in ["when", "use", "apply"]):
        return "pattern"

    return "pattern"  # Default


def parse_trigger_resolution(text: str) -> tuple:
    """Parse trigger and resolution from learning text.

    Formats:
        "trigger -> resolution"
        "When X, do Y"
        "X: Y"

    Args:
        text: Learning text

    Returns:
        (trigger, resolution) tuple
    """
    # Try -> separator
    if " -> " in text:
        parts = text.split(" -> ", 1)
        return parts[0].strip(), parts[1].strip()

    # Try : separator
    if ": " in text:
        parts = text.split(": ", 1)
        return parts[0].strip(), parts[1].strip()

    # Try "When X, Y" pattern
    match = re.match(r"When\s+(.+?),\s+(.+)", text, re.IGNORECASE)
    if match:
        return f"When {match.group(1)}", match.group(2)

    # Fallback: text is both trigger and resolution
    return text, ""


def extract_builder_candidates(transcript: str) -> List[dict]:
    """Extract learning candidates from builder transcript.

    Args:
        transcript: Full builder transcript

    Returns:
        List of candidate dicts
    """
    candidates = []

    # Try structured learned field
    learned = extract_learned_field(transcript)
    if learned:
        candidates.append({
            "type": learned.get("type", "pattern"),
            "trigger": learned.get("trigger", ""),
            "resolution": learned.get("resolution", ""),
            "confidence": "high",
            "source": "builder:structured",
        })

    # Also look for inline learnings
    # Pattern: "Learned: X" or "Note: X"
    for pattern in [r'Learned:\s*(.+?)(?:\n|$)', r'Note:\s*(.+?)(?:\n|$)']:
        for match in re.finditer(pattern, transcript, re.IGNORECASE):
            text = match.group(1).strip()
            if len(text) > 10:  # Skip very short notes
                mem_type = classify_learning(text)
                trigger, resolution = parse_trigger_resolution(text)
                candidates.append({
                    "type": mem_type,
                    "trigger": trigger,
                    "resolution": resolution,
                    "confidence": "medium",
                    "source": "builder:inline",
                })

    return candidates


def extract_explorer_candidates(transcript: str) -> List[dict]:
    """Extract learning candidates from explorer transcript.

    Args:
        transcript: Full explorer transcript

    Returns:
        List of candidate dicts (facts)
    """
    candidates = []
    findings = extract_findings_section(transcript)

    for finding in findings:
        if len(finding) > 15:  # Skip trivial findings
            candidates.append({
                "type": "fact",
                "trigger": finding,
                "resolution": "",  # Facts don't have resolutions
                "confidence": "medium",
                "source": "explorer:findings",
            })

    return candidates


def extract_planner_candidates(transcript: str) -> List[dict]:
    """Extract learning candidates from planner transcript.

    Args:
        transcript: Full planner transcript

    Returns:
        List of candidate dicts
    """
    candidates = []
    learned = extract_learned_block(transcript)

    for item in learned:
        mem_type = classify_learning(item)
        trigger, resolution = parse_trigger_resolution(item)

        candidates.append({
            "type": mem_type,
            "trigger": trigger,
            "resolution": resolution,
            "confidence": "medium",
            "source": "planner:learned",
        })

    return candidates


def process_transcript(
    agent_id: str,
    agent_type: str,
    transcript: str,
    tool_use_id: Optional[str] = None,
) -> dict:
    """Process agent transcript and extract learning candidates.

    Args:
        agent_id: Unique agent identifier
        agent_type: helix:helix-explorer, etc.
        transcript: Full agent transcript
        tool_use_id: Optional tool use ID for injection state lookup

    Returns:
        Learning queue entry dict
    """
    agent_short = agent_type.replace("helix:helix-", "")

    # Extract candidates by type
    if agent_short == "builder":
        candidates = extract_builder_candidates(transcript)
        outcome = extract_outcome(transcript)
    elif agent_short == "explorer":
        candidates = extract_explorer_candidates(transcript)
        outcome = "delivered"  # Explorers always "deliver" findings
    elif agent_short == "planner":
        candidates = extract_planner_candidates(transcript)
        outcome = "delivered"  # Planners always "deliver" plans
    else:
        candidates = []
        outcome = "unknown"

    # Get injected memories from injection state
    injected_memories = []
    if tool_use_id:
        state = get_injection_state(tool_use_id)
        if state:
            injected_memories = state.get("injected_memories", [])

    return {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "candidates": candidates,
        "injected_memories": injected_memories,
        "outcome": outcome,
    }


def write_to_queue(entry: dict) -> Path:
    """Write learning entry to queue.

    Args:
        entry: Learning queue entry dict

    Returns:
        Path to queue file
    """
    queue_dir = get_learning_queue_dir()
    queue_file = queue_dir / f"{entry['agent_id']}.json"
    queue_file.write_text(json.dumps(entry, indent=2))
    return queue_file


def process_hook_input(hook_input: dict) -> dict:
    """Process SubagentStop hook input.

    Args:
        hook_input: JSON from SubagentStop hook with:
            - agent_id: unique agent identifier
            - agent_type: helix:helix-explorer, etc.
            - agent_transcript_path: path to transcript file

    Returns:
        Hook response dict (typically empty, just side effects)
    """
    agent_type = hook_input.get("agent_type", "")

    # Only process helix agents
    if not agent_type.startswith("helix:helix-"):
        return {}

    agent_id = hook_input.get("agent_id", "")
    transcript_path = hook_input.get("agent_transcript_path", "")

    if not transcript_path or not Path(transcript_path).exists():
        return {}

    # Read transcript
    transcript = Path(transcript_path).read_text()

    # Get tool_use_id if available (for injection state lookup)
    tool_use_id = hook_input.get("tool_use_id")

    # Process and write to queue
    entry = process_transcript(
        agent_id=agent_id,
        agent_type=agent_type,
        transcript=transcript,
        tool_use_id=tool_use_id,
    )

    if entry["candidates"]:
        write_to_queue(entry)

    return {}


def main():
    """Main entry point - read from stdin, write to stdout."""
    try:
        input_data = sys.stdin.read()
        if not input_data.strip():
            print("{}")
            return

        hook_input = json.loads(input_data)
        result = process_hook_input(hook_input)
        print(json.dumps(result))

    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON: {e}"}), file=sys.stderr)
        print("{}")

    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        print("{}")


if __name__ == "__main__":
    main()
