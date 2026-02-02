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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


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


def extract_task_id(transcript: str) -> Optional[str]:
    """Extract TASK_ID from first user message in transcript.

    Transcript is JSONL. First line with user role contains TASK_ID: xxx

    Args:
        transcript: Full agent transcript (JSONL format)

    Returns:
        Task ID string or None
    """
    for line in transcript.split('\n'):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            # Check for user message
            role = entry.get('message', {}).get('role', entry.get('role', ''))
            if role == 'user':
                content = entry.get('message', {}).get('content', '')
                if isinstance(content, list):
                    content = ' '.join(
                        c.get('text', '') for c in content
                        if isinstance(c, dict) and c.get('type') == 'text'
                    )
                if isinstance(content, str):
                    match = re.search(r'TASK_ID:\s*(\S+)', content)
                    if match:
                        return match.group(1)
        except json.JSONDecodeError:
            continue
    return None


def extract_delivered_summary(transcript: str) -> Tuple[str, Optional[str]]:
    """Extract outcome and summary from assistant output.

    Parses from last assistant message for DELIVERED:/BLOCKED: markers.

    Args:
        transcript: Full agent transcript (JSONL format)

    Returns:
        (outcome, summary) tuple. outcome is "delivered", "blocked", or "unknown"
    """
    # Parse in reverse to find last assistant message
    lines = transcript.split('\n')
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            role = entry.get('message', {}).get('role', entry.get('role', ''))
            if role != 'assistant':
                continue

            content = entry.get('message', {}).get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    c.get('text', '') for c in content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )

            # Check for DELIVERED
            match = re.search(r'DELIVERED:\s*(.+?)(?:\n|$)', str(content))
            if match:
                return ("delivered", match.group(1).strip())

            # Check for BLOCKED
            match = re.search(r'BLOCKED:\s*(.+?)(?:\n|$)', str(content))
            if match:
                return ("blocked", match.group(1).strip())
        except json.JSONDecodeError:
            continue

    return ("unknown", None)


def write_task_status(task_id: str, agent_id: str, outcome: str, summary: Optional[str]):
    """Write task status entry for orchestrator polling.

    Appends to .helix/task-status.jsonl (append-only, ~100 bytes per entry).

    Args:
        task_id: Task ID from prompt
        agent_id: Agent ID from hook input
        outcome: "delivered", "blocked", or "unknown"
        summary: Summary text from DELIVERED/BLOCKED line
    """
    status_file = get_helix_dir() / "task-status.jsonl"
    entry = {
        "task_id": task_id,
        "agent_id": agent_id,
        "outcome": outcome,
        "summary": summary or "",
        "ts": datetime.now(timezone.utc).isoformat()
    }
    with open(status_file, 'a') as f:
        f.write(json.dumps(entry) + '\n')


def extract_explorer_findings(transcript: str) -> Optional[dict]:
    """Extract JSON findings block from explorer transcript.

    Looks for structured JSON output with status/findings in assistant messages.
    Returns the findings dict for orchestrator consumption.

    Args:
        transcript: Full agent transcript (JSONL format)

    Returns:
        Parsed findings dict or None
    """
    # Parse in reverse to find last assistant message with JSON
    for line in reversed(transcript.split('\n')):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            role = entry.get('message', {}).get('role', '')
            if role != 'assistant':
                continue

            content = entry.get('message', {}).get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    c.get('text', '') for c in content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )

            # Look for JSON with findings
            if '"findings"' not in str(content) and '"status"' not in str(content):
                continue

            # Find JSON block boundaries
            text = str(content)
            start = text.find('{')
            if start < 0:
                continue

            # Find matching closing brace
            depth = 0
            end = -1
            for i in range(start, len(text)):
                if text[i] == '{':
                    depth += 1
                elif text[i] == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break

            if end > start:
                try:
                    parsed = json.loads(text[start:end])
                    if 'findings' in parsed or 'status' in parsed:
                        return parsed
                except json.JSONDecodeError:
                    pass

        except json.JSONDecodeError:
            continue

    return None


def write_explorer_results(agent_id: str, findings: dict):
    """Write explorer findings to results directory.

    Orchestrator reads these small files instead of using TaskOutput.
    Each file is ~500 bytes vs 70KB+ from TaskOutput.

    Args:
        agent_id: Agent ID from hook input
        findings: Parsed findings dict from explorer
    """
    results_dir = get_helix_dir() / "explorer-results"
    results_dir.mkdir(exist_ok=True)

    result_file = results_dir / f"{agent_id}.json"
    result_file.write_text(json.dumps(findings, indent=2))


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


def apply_feedback(injected_memories: List[str], outcome: str) -> bool:
    """Apply feedback to injected memories based on outcome.

    This closes the feedback attribution loop directly in SubagentStop,
    making it independent of orchestrator TaskUpdate behavior.

    Args:
        injected_memories: List of memory names that were injected
        outcome: "delivered" or "blocked"

    Returns:
        True if feedback was applied, False otherwise
    """
    if not injected_memories or outcome not in ("delivered", "blocked"):
        return False

    # Determine delta based on outcome
    delta = 0.5 if outcome == "delivered" else -0.3

    try:
        # Import here to avoid circular imports
        from pathlib import Path
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from memory import feedback

        result = feedback(names=injected_memories, delta=delta)
        return result.get("updated", 0) > 0
    except Exception:
        return False


def cleanup_injection_state(tool_use_id: str) -> None:
    """Remove injection state file after feedback is applied.

    Args:
        tool_use_id: Tool use ID to clean up
    """
    if not tool_use_id:
        return

    state_dir = get_helix_dir() / "injection-state"
    state_file = state_dir / f"{tool_use_id}.json"

    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass


def extract_learned_field(transcript: str) -> Optional[dict]:
    """Extract `learned` JSON field from builder output.

    Builders output:
        learned: {"type": "...", "trigger": "...", "resolution": "..."}

    Args:
        transcript: Full agent transcript (JSONL format)

    Returns:
        Parsed learned dict or None
    """
    # Parse JSONL to get unescaped assistant content first
    # (raw transcript has escaped JSON: {\"type\": ...} which won't parse)
    for line in reversed(transcript.split('\n')):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            role = entry.get('message', {}).get('role', entry.get('role', ''))
            if role != 'assistant':
                continue

            content = entry.get('message', {}).get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    c.get('text', '') for c in content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )

            # Now search unescaped content for learned: pattern
            content_str = str(content)
            patterns = [
                r'learned:\s*(\{)',
                r'"learned":\s*(\{)',
                r'`learned`:\s*(\{)',
            ]

            for pattern in patterns:
                match = re.search(pattern, content_str, re.IGNORECASE)
                if match:
                    start = match.start(1)
                    text = content_str[start:]

                    # Extract balanced JSON object
                    depth = 0
                    end = 0
                    for i, char in enumerate(text):
                        if char == '{':
                            depth += 1
                        elif char == '}':
                            depth -= 1
                            if depth == 0:
                                end = i + 1
                                break

                    if end > 0:
                        try:
                            return json.loads(text[:end])
                        except json.JSONDecodeError:
                            continue

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


def extract_findings_section(transcript: str) -> List[dict]:
    """Extract findings from explorer transcript JSON output.

    Explorers output JSON with findings array:
        {"findings": [{"file": "...", "what": "...", ...}]}

    Contract mandates JSON. Markdown fallbacks removed - contract violations surface as empty results.

    Args:
        transcript: Full agent transcript

    Returns:
        List of finding dicts (empty if agent violates JSON contract)
    """
    findings_dict = extract_explorer_findings(transcript)
    if findings_dict and 'findings' in findings_dict:
        return findings_dict['findings']
    return []


def extract_learned_block(transcript: str) -> List[dict]:
    """Extract LEARNED block from planner transcript.

    Planners output JSON array after LEARNED:
        LEARNED: [
          {"type": "decision", "trigger": "chose X over Y", "resolution": "because Z"}
        ]

    Contract mandates JSON. Markdown fallbacks removed - contract violations surface as empty results.

    Args:
        transcript: Full agent transcript (JSONL format)

    Returns:
        List of learned dicts (empty if agent violates JSON contract)
    """
    # Parse JSONL to get unescaped assistant content
    for line in reversed(transcript.split('\n')):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            role = entry.get('message', {}).get('role', entry.get('role', ''))
            if role != 'assistant':
                continue

            content = entry.get('message', {}).get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    c.get('text', '') for c in content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )

            content_str = str(content)

            # JSON array extraction (per contract)
            match = re.search(r'LEARNED:\s*(\[)', content_str, re.IGNORECASE)
            if match:
                start = match.start(1)
                text = content_str[start:]

                # Extract balanced JSON array
                depth = 0
                end = 0
                for i, char in enumerate(text):
                    if char == '[':
                        depth += 1
                    elif char == ']':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break

                if end > 0:
                    try:
                        parsed = json.loads(text[:end])
                        if isinstance(parsed, list):
                            return parsed
                    except json.JSONDecodeError:
                        pass

        except json.JSONDecodeError:
            continue

    return []


def is_valid_learning(trigger: str, resolution: str) -> bool:
    """Validate learning candidate is not code noise.

    Args:
        trigger: Learning trigger text
        resolution: Learning resolution text

    Returns:
        True if valid learning, False if code noise
    """
    if len(trigger) > 300 or len(resolution) > 500:
        return False
    code_tokens = [
        'expect(', 'assert', 'def ', 'class ', '>>>',
        'at ', 'File "', 'Traceback', '    at ',
        '.toContain(', '.toBe(', 'describe(', 'it(',
        'import ', 'from ', 'require(', '});', '=> {'
    ]
    combined = trigger + resolution
    return not any(t in combined for t in code_tokens)


def extract_builder_candidates(transcript: str) -> List[dict]:
    """Extract learning candidates from builder transcript.

    Args:
        transcript: Full builder transcript

    Returns:
        List of candidate dicts
    """
    candidates = []

    # Only use structured learned field - inline extraction produces too much noise
    learned = extract_learned_field(transcript)
    if learned:
        trigger = learned.get("trigger", "")
        resolution = learned.get("resolution", "")
        if is_valid_learning(trigger, resolution):
            candidates.append({
                "type": learned.get("type", "pattern"),
                "trigger": trigger,
                "resolution": resolution,
                "confidence": "high",
                "source": "builder:structured",
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
        # Handle dict format (JSON output) or string (legacy)
        if isinstance(finding, dict):
            what = finding.get('what', '')
            file_path = finding.get('file', '')
            trigger = f"{file_path}: {what}" if file_path else what
        else:
            trigger = str(finding)

        if len(trigger) > 15:  # Skip trivial findings
            candidates.append({
                "type": "fact",
                "trigger": trigger,
                "resolution": "",  # Facts don't have resolutions
                "confidence": "medium",
                "source": "explorer:findings",
            })

    return candidates


def extract_planner_candidates(transcript: str) -> List[dict]:
    """Extract learning candidates from planner transcript.

    Contract mandates JSON LEARNED blocks. Non-dict items are skipped.

    Args:
        transcript: Full planner transcript

    Returns:
        List of candidate dicts
    """
    candidates = []
    learned = extract_learned_block(transcript)

    for item in learned:
        # Contract requires dict format - skip non-conformant items
        if not isinstance(item, dict):
            continue

        mem_type = item.get('type', 'decision')
        trigger = item.get('trigger', '')
        resolution = item.get('resolution', '')

        if trigger:  # Skip empty entries
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


def log_extraction_result(
    agent_id: str,
    agent_type: str,
    entry: dict,
    feedback_applied: Optional[bool] = None
):
    """Log extraction result for diagnostics.

    Args:
        agent_id: Agent identifier
        agent_type: Agent type string
        entry: Extraction result dict
        feedback_applied: Whether feedback was applied (None if not attempted)
    """
    log_file = get_helix_dir() / "extraction.log"
    ts = datetime.now(timezone.utc).isoformat()
    n_candidates = len(entry.get("candidates", []))
    outcome = entry.get("outcome", "unknown")
    n_injected = len(entry.get("injected_memories", []))

    status = "OK" if n_candidates > 0 else "EMPTY"
    log_parts = [
        ts,
        status,
        agent_type,
        agent_id,
        f"candidates={n_candidates}",
        f"outcome={outcome}",
    ]

    # Add feedback info for builders
    if feedback_applied is not None:
        log_parts.append(f"feedback={'applied' if feedback_applied else 'skipped'}({n_injected})")

    log_line = " | ".join(log_parts) + "\n"

    with open(log_file, 'a') as f:
        f.write(log_line)


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
    import time

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

    # Race condition fix: if builder has outcome but no candidates, retry once
    # (transcript file may not be fully flushed when hook fires)
    agent_short = agent_type.replace("helix:helix-", "")
    if agent_short == "builder" and not entry["candidates"] and entry["outcome"] == "delivered":
        time.sleep(0.1)  # Brief delay for filesystem sync
        transcript = Path(transcript_path).read_text()
        entry = process_transcript(
            agent_id=agent_id,
            agent_type=agent_type,
            transcript=transcript,
            tool_use_id=tool_use_id,
        )

    if entry["candidates"]:
        write_to_queue(entry)

    # Apply feedback directly for builders (closes loop without depending on TaskUpdate)
    # This is the primary feedback path - PostToolUse(TaskUpdate) serves as backup
    feedback_applied = None
    if agent_short == "builder" and entry["injected_memories"] and entry["outcome"] in ("delivered", "blocked"):
        feedback_applied = apply_feedback(entry["injected_memories"], entry["outcome"])
        if feedback_applied and tool_use_id:
            cleanup_injection_state(tool_use_id)

    # Diagnostic logging
    log_extraction_result(agent_id, agent_type, entry, feedback_applied)

    # Write task status for orchestrator polling (if TASK_ID present in prompt)
    task_id = extract_task_id(transcript)
    if task_id:
        outcome, summary = extract_delivered_summary(transcript)
        write_task_status(task_id, agent_id, outcome, summary)

    # Write explorer results for orchestrator (avoids TaskOutput context flood)
    agent_short = agent_type.replace("helix:helix-", "")
    if agent_short == "explorer":
        findings = extract_explorer_findings(transcript)
        if findings:
            write_explorer_results(agent_id, findings)

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
