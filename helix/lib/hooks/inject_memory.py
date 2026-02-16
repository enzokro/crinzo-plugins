#!/usr/bin/env python3
"""Memory injection for helix subagents at startup.

Called by SubagentStart hook. Recalls relevant insights and:
1. Returns additionalContext so the agent sees insights in context
2. Writes sideband file for SubagentStop feedback attribution

Architecture:
- Builders with orchestrator injection (batch_inject): sideband only, no additionalContext
- Builders without orchestrator injection: sideband + additionalContext
- Planners: always sideband + additionalContext (orchestrator never injects planners)
"""

import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from paths import get_helix_dir
from log import log_error as _log_error
from injection import format_insights, NO_PRIOR_MEMORY, NO_MATCHING_MEMORY, INSIGHTS_HEADER


def _log_injection(agent_id: str, agent_type: str, n_insights: int,
                   sideband: bool, context: bool):
    """Log successful injection for diagnostics."""
    try:
        log_file = get_helix_dir() / "extraction.log"
        ts = datetime.now(timezone.utc).isoformat()
        mode = []
        if sideband:
            mode.append("sideband")
        if context:
            mode.append("context")
        with open(log_file, 'a') as f:
            f.write(f"{ts} | INJECT | {agent_type} | {agent_id} | "
                    f"insights={n_insights} | {'+'.join(mode) or 'skip'}\n")
    except Exception:
        pass


def _parse_parent_transcript(transcript_path: str) -> tuple:
    """Parse parent transcript for objective and injection state in one pass.

    Reads last 50KB of parent transcript JSONL, finds the last Task tool_use
    targeting a helix agent, and extracts both the OBJECTIVE field and whether
    the prompt already contains INSIGHTS.

    Returns: (objective: str | None, has_insights: bool)
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return None, False

        # Read last 50KB to avoid loading huge transcripts
        size = path.stat().st_size
        with open(path, 'r') as f:
            if size > 50000:
                f.seek(size - 50000)
                f.readline()  # skip partial line
            raw = f.read()

        # Parse JSONL lines, find last Task tool_use prompt for helix agents
        last_prompt = None
        for line in raw.strip().splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
                content_blocks = entry.get('message', {}).get('content', [])
                if not isinstance(content_blocks, list):
                    continue

                for block in content_blocks:
                    if not isinstance(block, dict):
                        continue
                    if block.get('type') == 'tool_use' and block.get('name') == 'Task':
                        inp = block.get('input', {})
                        agent_type = inp.get('subagent_type', '')
                        if agent_type.startswith('helix:helix-'):
                            prompt = inp.get('prompt', '')
                            if prompt:
                                last_prompt = prompt
            except (json.JSONDecodeError, AttributeError):
                continue

        if not last_prompt:
            return None, False

        # Check if orchestrator already injected insights
        has_insights = INSIGHTS_HEADER in last_prompt

        # Extract OBJECTIVE field (stops at next uppercase FIELD: or end of string)
        objective = None
        match = re.search(r'OBJECTIVE:\s*(.+?)(?:\n[A-Z_]+:|$)', last_prompt, re.DOTALL)
        if match:
            objective = match.group(1).strip()[:1000]
        # No fallback: noisy prompt fragments pollute recall queries.
        # Caller handles None by returning NO_PRIOR_MEMORY.

        return objective, has_insights

    except Exception as e:
        _log_error("_parse_parent_transcript", e)
        return None, False


def _write_sideband(agent_id: str, names: List[str], objective: str = None,
                     query_embedding: str = None):
    """Write sideband file for SubagentStop feedback attribution.

    File: .helix/injected/{agent_id}.json
    Content: {"names": [...], "objective": "...", "query_embedding": "...(base64)"}

    The objective is the exact recall query used to select these insights,
    passed through to extract_learning for precise causal attribution.
    The query_embedding is the pre-computed embedding of the objective,
    avoiding redundant re-embedding during causal filtering.
    """
    try:
        injected_dir = get_helix_dir() / "injected"
        injected_dir.mkdir(exist_ok=True)
        sideband_file = injected_dir / f"{agent_id}.json"
        data = {"names": names}
        if objective:
            data["objective"] = objective
        if query_embedding:
            data["query_embedding"] = query_embedding
        sideband_file.write_text(json.dumps(data))
    except Exception as e:
        _log_error("_write_sideband", e)


def _format_additional_context(memories: list, total_insights: int = 0) -> dict:
    """Format recalled insights as additionalContext for the agent.

    Args:
        memories: List of recalled insight dicts
        total_insights: Total insights in DB (for cold-start signal accuracy)
    """
    if not memories:
        if total_insights > 0:
            return {"additionalContext": NO_MATCHING_MEMORY}
        return {"additionalContext": NO_PRIOR_MEMORY}

    insight_lines, names = format_insights(memories)

    lines = [INSIGHTS_HEADER]
    for line in insight_lines:
        lines.append(f"  - {line}")

    if names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(names)}")

    return {"additionalContext": "\n".join(lines)}


def _collect_already_injected() -> list:
    """Read names from existing sideband files for cross-agent diversity.

    During a wave, earlier-spawned agents write sideband files before later ones
    start. Reading these gives later agents different insight coverage without
    requiring process-level shared state.
    """
    try:
        injected_dir = get_helix_dir() / "injected"
        if not injected_dir.exists():
            return []
        names = []
        for f in injected_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                names.extend(data.get("names", []))
            except Exception:
                continue
        return names
    except Exception:
        return []


def process_hook_input(hook_input: dict) -> dict:
    """Process SubagentStart hook input.

    Two responsibilities:
    1. additionalContext: Agent sees insights in context (skipped if orchestrator already injected)
    2. Sideband file: INJECTED names for SubagentStop feedback (skipped if orchestrator injected)

    Sideband is skipped for orchestrator-injected builders because _extract_objective
    can't distinguish parallel Task tool_uses — all hooks would get the same (last)
    objective. Orchestrator-injected builders have authoritative INJECTED names in
    their transcript from format_prompt(); sideband would only add noise.

    For planners and gap-builders (no orchestrator injection), sideband is the
    primary feedback attribution source. If additionalContext doesn't appear in
    the subagent's JSONL transcript, feedback is attributed to insights the agent
    may not have seen — bounded by causal filtering and EMA's incremental weight.
    """
    agent_type = hook_input.get("agent_type", "")
    if not agent_type.startswith("helix:helix-"):
        return {}

    agent_id = hook_input.get("agent_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    if not agent_id:
        return {}

    # Parse parent transcript once for both objective and injection state
    objective, already_injected = _parse_parent_transcript(transcript_path) if transcript_path else (None, False)
    if not objective:
        _log_injection(agent_id, agent_type, 0, False, True)
        return {"additionalContext": NO_PRIOR_MEMORY}
    if already_injected:
        _log_injection(agent_id, agent_type, 0, False, False)
        return {}

    # Collect already-injected names from sibling agents for cross-agent diversity
    suppress_names = _collect_already_injected()

    # Recall relevant insights
    total_insights = 0
    try:
        from memory.core import recall
        memories = recall(objective, limit=5, suppress_names=suppress_names or None)
        if not memories:
            from memory.core import count
            total_insights = count()
    except Exception as e:
        _log_error("recall", e)
        memories = []

    names = [m.get("name", "") for m in memories if m.get("name")]

    # Write sideband file for SubagentStop feedback attribution
    # Include cached query embedding to avoid redundant re-embedding in extract hook
    wrote_sideband = False
    if names:
        query_emb_b64 = None
        try:
            from memory.embeddings import embed as _embed, to_blob as _to_blob
            emb_tuple = _embed(objective, is_query=True)  # LRU cache hit from recall()
            if emb_tuple:
                query_emb_b64 = base64.b64encode(_to_blob(emb_tuple)).decode('ascii')
        except Exception:
            pass  # embedding unavailable — extract hook will recompute
        _write_sideband(agent_id, names, objective=objective, query_embedding=query_emb_b64)
        wrote_sideband = True

    result = _format_additional_context(memories, total_insights=total_insights)
    _log_injection(agent_id, agent_type, len(names), wrote_sideband, "additionalContext" in result)
    return result


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
