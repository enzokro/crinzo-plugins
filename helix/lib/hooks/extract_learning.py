#!/usr/bin/env python3
"""Learning extraction from helix agent transcripts.

Called by SubagentStop hook. Parses agent transcripts for insights
and applies feedback to injected memories.

Unified extraction pattern:
    - INSIGHT: {"content": "When X, do Y because Z", "tags": [...]}
    - DELIVERED: <summary>
    - BLOCKED: <reason>
    - INJECTED: ["name1", "name2"]

Output written to .helix/learning-queue/{agent_id}.json
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction import extract_insight, extract_outcome, extract_injected_names, process_completion


def get_helix_dir() -> Path:
    """Get .helix directory using ancestor search."""
    project_dir = os.environ.get("HELIX_PROJECT_DIR")
    if project_dir:
        helix_dir = Path(project_dir) / ".helix"
        helix_dir.mkdir(exist_ok=True)
        return helix_dir

    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        helix_dir = parent / ".helix"
        if helix_dir.exists() and helix_dir.is_dir():
            return helix_dir

    helix_dir = cwd / ".helix"
    helix_dir.mkdir(exist_ok=True)
    return helix_dir


def get_learning_queue_dir() -> Path:
    """Get learning queue directory."""
    queue_dir = get_helix_dir() / "learning-queue"
    queue_dir.mkdir(exist_ok=True)
    return queue_dir


def extract_task_id(transcript: str) -> Optional[str]:
    """Extract TASK_ID from transcript."""
    for line in transcript.split('\n'):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
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


def get_full_transcript_text(transcript: str) -> str:
    """Extract full text from JSONL transcript."""
    text_parts = []
    for line in transcript.split('\n'):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            content = entry.get('message', {}).get('content', '')
            if isinstance(content, list):
                content = ' '.join(
                    c.get('text', '') for c in content
                    if isinstance(c, dict) and c.get('type') == 'text'
                )
            if content:
                text_parts.append(str(content))
        except json.JSONDecodeError:
            continue
    return '\n'.join(text_parts)


def write_task_status(task_id: str, agent_id: str, outcome: str, summary: Optional[str]):
    """Write task status for orchestrator polling."""
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


def extract_explorer_findings(transcript_text: str) -> Optional[dict]:
    """Extract JSON findings from explorer transcript."""
    if '"findings"' not in transcript_text and '"status"' not in transcript_text:
        return None

    start = transcript_text.find('{')
    if start < 0:
        return None

    depth = 0
    end = -1
    for i in range(start, len(transcript_text)):
        if transcript_text[i] == '{':
            depth += 1
        elif transcript_text[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end > start:
        try:
            parsed = json.loads(transcript_text[start:end])
            if 'findings' in parsed or 'status' in parsed:
                return parsed
        except json.JSONDecodeError:
            pass

    return None


def write_explorer_results(agent_id: str, findings: dict):
    """Write explorer findings for orchestrator."""
    results_dir = get_helix_dir() / "explorer-results"
    results_dir.mkdir(exist_ok=True)
    result_file = results_dir / f"{agent_id}.json"
    result_file.write_text(json.dumps(findings, indent=2))


def apply_feedback(injected_names: list, outcome: str) -> bool:
    """Apply feedback to injected insights based on outcome."""
    if not injected_names or outcome not in ("delivered", "blocked"):
        return False

    try:
        from memory import feedback
        result = feedback(names=injected_names, outcome=outcome)
        return result.get("updated", 0) > 0
    except Exception:
        return False


def store_insight(insight: dict) -> Optional[str]:
    """Store extracted insight."""
    if not insight or not insight.get("content"):
        return None

    try:
        from memory import store
        result = store(content=insight["content"], tags=insight.get("tags", []))
        if result.get("status") in ("added", "merged"):
            return result.get("name")
    except Exception:
        pass
    return None


def log_extraction_result(agent_id: str, agent_type: str, result: dict, feedback_applied: Optional[bool] = None):
    """Log extraction result for diagnostics."""
    log_file = get_helix_dir() / "extraction.log"
    ts = datetime.now(timezone.utc).isoformat()
    outcome = result.get("outcome", "unknown")
    has_insight = result.get("insight") is not None
    n_injected = len(result.get("injected", []))

    log_parts = [
        ts,
        "OK" if has_insight else "NO_INSIGHT",
        agent_type,
        agent_id,
        f"outcome={outcome}",
    ]

    if feedback_applied is not None:
        log_parts.append(f"feedback={'applied' if feedback_applied else 'skipped'}({n_injected})")

    with open(log_file, 'a') as f:
        f.write(" | ".join(log_parts) + "\n")


def process_hook_input(hook_input: dict) -> dict:
    """Process SubagentStop hook input."""
    agent_type = hook_input.get("agent_type", "")

    if not agent_type.startswith("helix:helix-"):
        return {}

    agent_id = hook_input.get("agent_id", "")
    transcript_path = hook_input.get("agent_transcript_path", "")

    if not transcript_path or not Path(transcript_path).exists():
        return {}

    # Read and parse transcript
    transcript_raw = Path(transcript_path).read_text()
    transcript_text = get_full_transcript_text(transcript_raw)

    # Process with unified extraction
    result = process_completion(transcript_text, agent_type.replace("helix:helix-", ""))

    # Retry for builders if outcome not yet flushed
    agent_short = agent_type.replace("helix:helix-", "")
    if agent_short == "builder" and result["outcome"] == "unknown":
        for delay in [0.15, 0.35, 0.75]:
            time.sleep(delay)
            transcript_raw = Path(transcript_path).read_text()
            transcript_text = get_full_transcript_text(transcript_raw)
            result = process_completion(transcript_text, agent_short)
            if result["outcome"] != "unknown":
                break

    # Store insight if extracted
    stored_name = None
    if result.get("insight"):
        stored_name = store_insight(result["insight"])

    # Apply feedback to injected insights
    feedback_applied = None
    if result["injected"] and result["outcome"] in ("delivered", "blocked"):
        feedback_applied = apply_feedback(result["injected"], result["outcome"])

    # Log result
    log_extraction_result(agent_id, agent_type, result, feedback_applied)

    # Write task status for orchestrator polling
    task_id = extract_task_id(transcript_raw)
    if task_id:
        summary_match = re.search(r'(?:DELIVERED|BLOCKED):\s*(.+?)(?:\n|$)', transcript_text, re.IGNORECASE)
        summary = summary_match.group(1).strip() if summary_match else None
        write_task_status(task_id, agent_id, result["outcome"], summary)

    # Write explorer results for orchestrator
    if agent_short == "explorer":
        findings = extract_explorer_findings(transcript_text)
        if findings:
            write_explorer_results(agent_id, findings)

    return {}


def main():
    """Main entry point."""
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
