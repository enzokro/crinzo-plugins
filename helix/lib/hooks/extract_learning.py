#!/usr/bin/env python3
"""Learning extraction from helix agent transcripts.

Called by SubagentStop hook. Extracts insights and applies feedback synchronously.

Extraction patterns:
    - INSIGHT: {"content": "When X, do Y because Z", "tags": [...]}
    - DELIVERED: <summary>
    - BLOCKED: <reason>
    - INJECTED: ["name1", "name2"]

On completion:
    - Stores extracted insight via memory.store()
    - Applies feedback to injected insights via memory.feedback()
    - Writes task status to .helix/task-status.jsonl
    - Logs to .helix/extraction.log
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction import extract_insight, extract_outcome, extract_injected_names, process_completion
from paths import get_helix_dir


def _transcript_has_error(transcript_raw: str) -> bool:
    """Check if transcript's last entry indicates agent crash/API error."""
    lines = [l for l in transcript_raw.strip().splitlines() if l.strip()]
    if not lines:
        return True  # empty transcript = crashed
    try:
        last = json.loads(lines[-1])
        # Check for error indicators in last entry
        if last.get("type") == "error" or last.get("error"):
            return True
        # Check for API error in message content
        msg = last.get("message", {})
        if msg.get("stop_reason") == "error":
            return True
    except json.JSONDecodeError:
        pass
    return False


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


def write_task_status(task_id: str, agent_id: str, outcome: str, summary: Optional[str],
                      insight_content: Optional[str] = None):
    """Write task status for orchestrator polling.

    Args:
        task_id: Task identifier
        agent_id: Agent identifier
        outcome: "delivered" or "blocked"
        summary: Task completion summary
        insight_content: Content of extracted insight (for wave synthesis + orchestrator visibility)
    """
    status_file = get_helix_dir() / "task-status.jsonl"
    entry = {
        "task_id": task_id,
        "agent_id": agent_id,
        "outcome": outcome,
        "summary": summary or "",
        "ts": datetime.now(timezone.utc).isoformat()
    }
    if insight_content:
        entry["insight"] = insight_content
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


def filter_causal_insights(injected_names: list, task_context: str) -> list:
    """Filter injected insights to those causally relevant to the task.

    Computes semantic similarity between each injected insight's content
    and the task context (objective + delivery summary). Only insights
    passing the threshold are considered causally relevant.

    Args:
        injected_names: Names of insights that were injected
        task_context: Combined task objective + delivered summary text

    Returns: Subset of injected_names that pass causal similarity check
    """
    if not injected_names or not task_context.strip():
        return injected_names  # graceful fallback

    try:
        from memory.embeddings import embed, cosine
        from memory.core import get, CAUSAL_SIMILARITY_THRESHOLD

        context_emb = embed(task_context, is_query=True)
        if not context_emb:
            return injected_names  # no embeddings available, treat all as causal

        causal = []
        for name in injected_names:
            insight = get(name)
            if not insight:
                continue
            insight_emb = embed(insight["content"], is_query=False)
            if not insight_emb:
                causal.append(name)  # can't check, assume causal
                continue
            if cosine(context_emb, insight_emb) >= CAUSAL_SIMILARITY_THRESHOLD:
                causal.append(name)

        return causal
    except Exception:
        return injected_names  # on any error, treat all as causal


def apply_feedback(injected_names: list, outcome: str, causal_names: list = None) -> bool:
    """Apply feedback to injected insights based on outcome.

    Args:
        injected_names: All insight names that were injected
        outcome: "delivered" or "blocked"
        causal_names: Subset that passed causal check (None = all causal)
    """
    if not injected_names or outcome not in ("delivered", "blocked", "plan_complete"):
        return False

    try:
        from memory.core import feedback
        result = feedback(names=injected_names, outcome=outcome, causal_names=causal_names)
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


def log_extraction_result(agent_id: str, agent_type: str, result: dict,
                          feedback_applied: Optional[bool] = None,
                          causal_count: Optional[int] = None,
                          total_injected: Optional[int] = None):
    """Log extraction result for diagnostics."""
    log_file = get_helix_dir() / "extraction.log"
    ts = datetime.now(timezone.utc).isoformat()
    outcome = result.get("outcome", "unknown")
    has_insight = result.get("insight") is not None
    n_injected = total_injected if total_injected is not None else len(result.get("injected", []))

    log_parts = [
        ts,
        "OK" if has_insight else "NO_INSIGHT",
        agent_type,
        agent_id,
        f"outcome={outcome}",
    ]

    if feedback_applied is not None:
        log_parts.append(f"feedback={'applied' if feedback_applied else 'skipped'}({n_injected})")

    if causal_count is not None:
        log_parts.append(f"causal={causal_count}/{n_injected}")

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
    result = process_completion(transcript_text)

    # Retry for builders if outcome not yet flushed
    agent_short = agent_type.replace("helix:helix-", "")
    if agent_short in ("builder", "planner") and result["outcome"] == "unknown":
        if _transcript_has_error(transcript_raw):
            result["outcome"] = "crashed"
        else:
            for delay in [0.15, 0.35, 0.75]:
                time.sleep(delay)
                transcript_raw = Path(transcript_path).read_text()
                transcript_text = get_full_transcript_text(transcript_raw)
                result = process_completion(transcript_text)
                if result["outcome"] != "unknown":
                    break

    # Store insight if extracted
    stored_name = None
    if result.get("insight"):
        stored_name = store_insight(result["insight"])

    # Build task context for causal filtering
    task_parts = re.findall(r'(?:TASK|OBJECTIVE):\s*(.+)', transcript_text, re.IGNORECASE)
    summary_parts = re.findall(r'(?:DELIVERED|BLOCKED):\s*(.+)', transcript_text, re.IGNORECASE)
    task_context = " ".join(task_parts[-2:]) + " " + (summary_parts[-1] if summary_parts else "")

    # Filter to causally relevant insights, then apply feedback
    feedback_applied = None
    causal_names = None
    if result["injected"] and result["outcome"] in ("delivered", "blocked", "plan_complete"):
        causal_names = filter_causal_insights(result["injected"], task_context.strip())
        feedback_applied = apply_feedback(result["injected"], result["outcome"], causal_names=causal_names)

    # Log result with causal stats
    n_causal = len(causal_names) if causal_names is not None else None
    n_injected = len(result.get("injected", []))
    log_extraction_result(agent_id, agent_type, result, feedback_applied,
                          causal_count=n_causal, total_injected=n_injected)

    # Write task status for orchestrator polling (with insight content for wave synthesis)
    task_id = extract_task_id(transcript_raw)
    if task_id:
        summary = summary_parts[-1].strip()[:200] if summary_parts else None
        insight_content = result["insight"]["content"] if result.get("insight") else None
        write_task_status(task_id, agent_id, result["outcome"], summary,
                          insight_content=insight_content)

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
