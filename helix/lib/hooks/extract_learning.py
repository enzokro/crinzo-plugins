#!/usr/bin/env python3
"""Learning extraction from helix agent transcripts.

Called by SubagentStop hook. Extracts insights and applies feedback synchronously.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from extraction import process_completion
from paths import get_helix_dir
from log import log_error as _log_error


def _get_text_content(entry: dict) -> str:
    """Extract text content from a transcript entry."""
    content = entry.get('message', {}).get('content', '')
    if isinstance(content, list):
        content = ' '.join(
            c.get('text', '') for c in content
            if isinstance(c, dict) and c.get('type') == 'text'
        )
    return str(content) if content else ''


def _parse_transcript(transcript_raw: str) -> SimpleNamespace:
    """Parse JSONL transcript in a single pass, extracting all needed fields."""
    result = SimpleNamespace(full_text="", last_assistant_text=None, task_id=None, has_error=True)
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
            result.has_error = (
                entry.get("type") == "error"
                or entry.get("error")
                or entry.get("message", {}).get("stop_reason") == "error"
            )

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
    """Write task status for orchestrator polling."""
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
    """Extract JSON findings from explorer transcript (scans backwards)."""
    if not transcript_text:
        return None
    if '"findings"' not in transcript_text and '"status"' not in transcript_text:
        return None

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
        end = transcript_text.rfind('}', 0, end)

    return None


def write_explorer_results(agent_id: str, findings: dict):
    """Write explorer findings for orchestrator."""
    results_dir = get_helix_dir() / "explorer-results"
    results_dir.mkdir(exist_ok=True)
    result_file = results_dir / f"{agent_id}.json"
    result_file.write_text(json.dumps(findings, indent=2))


def filter_causal_insights(injected_names: list, task_context: str,
                           context_embedding: bytes = None) -> list:
    """Filter injected insights to those causally relevant to the task."""
    if not injected_names or not task_context.strip():
        return []

    try:
        import numpy as np
        from memory.core import CAUSAL_SIMILARITY_THRESHOLD
        from memory.embeddings import build_embedding_matrix
        from db.connection import get_db

        if context_embedding is not None:
            ctx_vec = np.frombuffer(context_embedding, dtype=np.float32)
        else:
            from memory.embeddings import embed
            context_emb = embed(task_context, is_query=True)
            if not context_emb:
                return []
            ctx_vec = np.array(context_emb, dtype=np.float32)

        db = get_db()
        placeholders = ",".join("?" for _ in injected_names)
        rows_by_name = {
            r["name"]: r for r in db.execute(
                f"SELECT name, embedding FROM insight WHERE name IN ({placeholders})",
                injected_names
            ).fetchall()
        }

        # Build parallel lists, then vectorized matmul
        valid = [
            (name, rows_by_name[name]["embedding"])
            for name in injected_names
            if name in rows_by_name and rows_by_name[name]["embedding"]
        ]

        if not valid:
            return []

        valid_names, emb_data = zip(*valid)
        mat = build_embedding_matrix(list(emb_data))
        sims = mat @ ctx_vec
        return [name for name, sim in zip(valid_names, sims) if sim >= CAUSAL_SIMILARITY_THRESHOLD]
    except Exception as e:
        _log_error("filter_causal_insights", e)
        return []


def _read_sideband(agent_id: str) -> tuple:
    """Read and clean up sideband file. Returns (names, objective, query_embedding)."""
    try:
        sideband_file = get_helix_dir() / "injected" / f"{agent_id}.json"
        if not sideband_file.exists():
            return [], None, None

        data = json.loads(sideband_file.read_text())
        names = data.get("names", [])
        objective = data.get("objective")

        query_embedding = None
        raw_emb = data.get("query_embedding")
        if raw_emb:
            import base64
            query_embedding = base64.b64decode(raw_emb)

        sideband_file.unlink(missing_ok=True)
        return names, objective, query_embedding
    except Exception as e:
        _log_error("_read_sideband", e)
        return [], None, None


def apply_feedback(injected_names: list, outcome: str, causal_names: list = None) -> bool:
    """Apply feedback to injected insights based on outcome."""
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
    """Store extracted insight. Derived insights start at lower effectiveness (0.35)."""
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
    has_insight = result.get("insight") is not None
    n_injected = total_injected if total_injected is not None else len(result.get("injected", []))

    log_parts = [ts, "OK" if has_insight else "NO_INSIGHT", agent_type, agent_id,
                 f"outcome={result.get('outcome', 'unknown')}"]

    if feedback_applied is not None:
        log_parts.append(f"feedback={'applied' if feedback_applied else 'skipped'}({n_injected})")
    if causal_count is not None:
        log_parts.append(f"causal={causal_count}/{n_injected}")

    with open(log_file, 'a') as f:
        f.write(" | ".join(log_parts) + "\n")


def _create_provenance_edges(child_name: str, parent_names: list) -> None:
    """Create led_to edges from causal parent insights to a newly stored child."""
    from db.connection import get_db
    from memory.edges import add_edges

    db = get_db()
    child_row = db.execute("SELECT id FROM insight WHERE name = ?", (child_name,)).fetchone()
    if not child_row:
        return

    placeholders = ",".join("?" for _ in parent_names)
    parent_rows = db.execute(
        f"SELECT id FROM insight WHERE name IN ({placeholders})", parent_names
    ).fetchall()
    if parent_rows:
        add_edges([(r["id"], child_row["id"], 1.0, "led_to") for r in parent_rows])


def process_hook_input(hook_input: dict) -> dict:
    """Process SubagentStop hook input.

    Three-phase pipeline -- handoff files written before any embedding/DB work:
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

    # Read and parse transcript
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
                    _log_error("transcript_retry", f"retry {delay}s resolved outcome to {result['outcome']}")
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
    stored_name = None
    if result.get("insight"):
        stored_name = store_insight(result["insight"])

    # 3b: Feedback attribution (independent of store success)
    feedback_applied = None
    causal_names = None
    all_injected = []
    try:
        injected_from_sideband, sideband_objective, sideband_embedding = _read_sideband(agent_id)
        all_injected = list(set(injected_from_sideband + result["injected"]))

        if sideband_objective:
            task_context = sideband_objective
            embedding_for_causal = sideband_embedding
        else:
            task_parts = result.get("task_parts", [])
            task_context = " ".join(task_parts[-2:]) + " " + (summary_parts[-1] if summary_parts else "")
            embedding_for_causal = None

        feedback_outcome = result["outcome"]
        if feedback_outcome == "crashed":
            feedback_outcome = "blocked"
        if all_injected and feedback_outcome in ("delivered", "blocked", "plan_complete"):
            causal_names = filter_causal_insights(all_injected, task_context.strip(),
                                                  context_embedding=embedding_for_causal)
            feedback_applied = apply_feedback(all_injected, feedback_outcome, causal_names=causal_names)
    except Exception as e:
        _log_error("feedback_attribution", e)

    # 3d: Provenance edges (independent error boundary)
    if stored_name and causal_names:
        try:
            _create_provenance_edges(stored_name, causal_names)
        except Exception as e:
            _log_error("provenance_edges", e)

    # 3c: Log result (independent of store/feedback success)
    try:
        n_causal = len(causal_names) if causal_names is not None else None
        n_injected = len(all_injected)
        log_extraction_result(agent_id, agent_type, result, feedback_applied,
                              causal_count=n_causal, total_injected=n_injected)
    except Exception as e:
        _log_error("log_extraction_result", e)

    return {}


if __name__ == "__main__":
    from common import run_hook
    run_hook(process_hook_input)
