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

from extraction import process_completion
from paths import get_helix_dir
from log import log_error as _log_error


def _get_text_content(entry: dict) -> str:
    """Extract text content from a transcript entry.

    Handles both string content and list content (array of {type, text} blocks).
    """
    content = entry.get('message', {}).get('content', '')
    if isinstance(content, list):
        content = ' '.join(
            c.get('text', '') for c in content
            if isinstance(c, dict) and c.get('type') == 'text'
        )
    return str(content) if content else ''


class _ParsedTranscript:
    """Result of single-pass JSONL transcript parsing."""
    __slots__ = ('full_text', 'last_assistant_text', 'task_id', 'has_error')

    def __init__(self):
        self.full_text = ""
        self.last_assistant_text = None
        self.task_id = None
        self.has_error = True  # default: empty = crashed


def _parse_transcript(transcript_raw: str) -> _ParsedTranscript:
    """Parse JSONL transcript in a single pass, extracting all needed fields.

    Returns _ParsedTranscript with:
        - full_text: concatenated text from all entries
        - last_assistant_text: text from the final assistant message
        - task_id: TASK_ID from first user message containing it
        - has_error: whether the last entry indicates a crash/API error
    """
    result = _ParsedTranscript()
    text_parts = []
    lines = [l for l in transcript_raw.strip().splitlines() if l.strip()]

    if not lines:
        return result

    for i, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        # Check for error in last entry
        if i == len(lines) - 1:
            result.has_error = False
            if entry.get("type") == "error" or entry.get("error"):
                result.has_error = True
            elif entry.get("message", {}).get("stop_reason") == "error":
                result.has_error = True

        role = entry.get('message', {}).get('role', entry.get('role', ''))
        content = _get_text_content(entry)

        if content:
            text_parts.append(content)

        if role == 'user' and content and result.task_id is None:
            match = re.search(r'TASK_ID:\s*(\S+)', content)
            if match:
                result.task_id = match.group(1)

        if role == 'assistant' and content and content.strip():
            result.last_assistant_text = content.strip()

    result.full_text = '\n'.join(text_parts)
    return result


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
    """Extract JSON findings from explorer transcript.

    Scans backwards from end of text — the explorer's JSON output is
    typically the last JSON object in the transcript.
    """
    if not transcript_text:
        return None
    if '"findings"' not in transcript_text and '"status"' not in transcript_text:
        return None

    # Search backwards — explorer JSON is last output
    end = transcript_text.rfind('}')
    while end >= 0:
        depth = 0
        start = -1
        for i in range(end, -1, -1):
            if transcript_text[i] == '}':
                depth += 1
            elif transcript_text[i] == '{':
                depth -= 1
            if depth == 0:
                start = i
                break
        if start >= 0:
            try:
                parsed = json.loads(transcript_text[start:end + 1])
                if 'findings' in parsed or 'status' in parsed:
                    return parsed
            except json.JSONDecodeError:
                pass
        # Try next-to-last }
        end = transcript_text.rfind('}', 0, end)

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
        import numpy as np
        from memory.embeddings import embed
        from memory.core import CAUSAL_SIMILARITY_THRESHOLD
        from db.connection import get_db

        context_emb = embed(task_context, is_query=True)
        if not context_emb:
            return []  # embeddings unavailable — conservative: no feedback rather than undiscriminating

        # Batch-fetch all embeddings in one query instead of N individual SELECTs
        db = get_db()
        placeholders = ",".join("?" for _ in injected_names)
        rows_by_name = {
            r["name"]: r for r in db.execute(
                f"SELECT name, embedding FROM insight WHERE name IN ({placeholders})",
                injected_names
            ).fetchall()
        }

        # Vectorized: single matmul instead of per-insight cosine()
        causal = []
        emb_data = []
        valid_names = []
        for name in injected_names:
            row = rows_by_name.get(name)
            if not row:
                continue  # insight doesn't exist in DB
            if not row["embedding"]:
                causal.append(name)  # exists but no embedding, assume causal
                continue
            emb_data.append(row["embedding"])
            valid_names.append(name)

        if emb_data:
            mat = np.frombuffer(b''.join(emb_data), dtype=np.float32).reshape(len(emb_data), -1)
            ctx_vec = np.array(context_emb, dtype=np.float32)
            sims = mat @ ctx_vec
            for i, name in enumerate(valid_names):
                if sims[i] >= CAUSAL_SIMILARITY_THRESHOLD:
                    causal.append(name)

        return causal
    except Exception as e:
        _log_error("filter_causal_insights", e)
        return []  # on error, conservative: no feedback rather than undiscriminating


def _read_sideband(agent_id: str) -> tuple:
    """Read and clean up sideband file written by SubagentStart hook.

    File: .helix/injected/{agent_id}.json
    Returns: (names: list, objective: str|None)
    Deletes file after reading.
    """
    try:
        sideband_file = get_helix_dir() / "injected" / f"{agent_id}.json"
        if not sideband_file.exists():
            return [], None

        data = json.loads(sideband_file.read_text())
        names = data.get("names", [])
        objective = data.get("objective")

        # Clean up
        sideband_file.unlink(missing_ok=True)

        return names, objective
    except Exception as e:
        _log_error("_read_sideband", e)
        return [], None


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
    except Exception as e:
        _log_error("apply_feedback", e)
        return False


def store_insight(insight: dict) -> Optional[str]:
    """Store extracted insight.

    Derived insights (from BLOCKED fallback) start at lower effectiveness (0.35)
    so they rank below explicit INSIGHT: extractions until proven by causal feedback.
    """
    if not insight or not insight.get("content"):
        return None

    try:
        from memory import store
        kwargs = {"content": insight["content"], "tags": insight.get("tags", [])}
        if insight.get("derived"):
            kwargs["initial_effectiveness"] = 0.35
        result = store(**kwargs)
        if result.get("status") in ("added", "merged"):
            return result.get("name")
    except Exception as e:
        _log_error("store_insight", e)
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
    """Process SubagentStop hook input.

    Three-phase pipeline — handoff files written before any embedding/DB work:
      Phase 1: Explorer results (transcript parsing only)
      Phase 2: Outcome determination + task status write
      Phase 3: Optional insight storage, causal filtering, feedback (best-effort)
    """
    agent_type = hook_input.get("agent_type", "")

    if not agent_type.startswith("helix:helix-"):
        return {}

    agent_id = hook_input.get("agent_id", "")
    if not agent_id:
        return {}

    transcript_path = hook_input.get("agent_transcript_path", "")

    if not transcript_path or not Path(transcript_path).exists():
        return {}

    # Read and parse transcript — single pass extracts all fields
    transcript_raw = Path(transcript_path).read_text()
    parsed = _parse_transcript(transcript_raw)
    transcript_text = parsed.full_text
    agent_short = agent_type.replace("helix:helix-", "")

    # --- Phase 1: Write explorer results (transcript parsing only, no DB) ---
    if agent_short == "explorer":
        try:
            findings = extract_explorer_findings(parsed.last_assistant_text) if parsed.last_assistant_text else None
            if not findings:
                findings = extract_explorer_findings(transcript_text)
            if findings:
                write_explorer_results(agent_id, findings)
            else:
                log_extraction_result(agent_id, agent_type,
                                      {"outcome": "explorer_extraction_failed"})
        except Exception as e:
            _log_error("explorer_results_write", e)

    # --- Phase 2: Outcome determination + task status write ---
    result = process_completion(transcript_text)

    if agent_short in ("builder", "planner") and result["outcome"] == "unknown":
        if parsed.has_error:
            result["outcome"] = "crashed"
        else:
            for delay in [0.15, 0.35, 0.75]:
                time.sleep(delay)
                transcript_raw = Path(transcript_path).read_text()
                reparsed = _parse_transcript(transcript_raw)
                transcript_text = reparsed.full_text
                result = process_completion(transcript_text)
                if result["outcome"] != "unknown":
                    break

    summary_parts = result.get("summary_parts", [])
    task_id = parsed.task_id

    if task_id:
        try:
            summary = summary_parts[-1].strip()[:200] if summary_parts else None
            insight_content = result["insight"]["content"] if result.get("insight") else None
            write_task_status(task_id, agent_id, result["outcome"], summary,
                              insight_content=insight_content)
        except Exception as e:
            _log_error("task_status_write", e)

    # --- Phase 3: Optional insight processing (best-effort, independent error boundaries) ---

    # 3a: Store extracted insight
    try:
        if result.get("insight"):
            store_insight(result["insight"])
    except Exception as e:
        _log_error("store_insight", e)

    # 3b: Feedback attribution (independent of store success)
    feedback_applied = None
    causal_names = None
    all_injected = []
    try:
        injected_from_sideband, sideband_objective = _read_sideband(agent_id)
        all_injected = list(set(injected_from_sideband + result["injected"]))

        # Prefer sideband objective (exact recall query) over transcript reconstruction
        if sideband_objective:
            task_context = sideband_objective
        else:
            task_parts = result.get("task_parts", [])
            task_context = " ".join(task_parts[-2:]) + " " + (summary_parts[-1] if summary_parts else "")

        feedback_outcome = result["outcome"]
        # Treat crashed agents as blocked — insights correlated with crashes should be penalized
        if feedback_outcome == "crashed":
            feedback_outcome = "blocked"
        if all_injected and feedback_outcome in ("delivered", "blocked", "plan_complete"):
            causal_names = filter_causal_insights(all_injected, task_context.strip())
            feedback_applied = apply_feedback(all_injected, feedback_outcome, causal_names=causal_names)
    except Exception as e:
        _log_error("feedback_attribution", e)

    # 3c: Log result (independent of store/feedback success)
    try:
        n_causal = len(causal_names) if causal_names is not None else None
        n_injected = len(all_injected)
        log_extraction_result(agent_id, agent_type, result, feedback_applied,
                              causal_count=n_causal, total_injected=n_injected)
    except Exception as e:
        _log_error("log_extraction_result", e)

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
