#!/usr/bin/env python3
"""Memory injection for helix subagents at startup.

Called by SubagentStart hook. Recalls relevant insights and:
1. Returns additionalContext so the agent sees insights in context
2. Writes sideband file for SubagentStop feedback attribution
"""

import base64
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, NamedTuple, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from paths import get_helix_dir
from log import log_error as _log_error
from injection import format_insights, NO_PRIOR_MEMORY, NO_MATCHING_MEMORY, INSIGHTS_HEADER


class ParsedTranscript(NamedTuple):
    objective: Optional[str]
    has_insights: bool
    constraints: Optional[str]
    risk_areas: Optional[str]


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


def _parse_parent_transcript(transcript_path: str) -> ParsedTranscript:
    """Parse parent transcript for objective, injection state, constraints, and risk areas.

    Returns: ParsedTranscript(objective, has_insights, constraints, risk_areas)
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return ParsedTranscript(None, False, None, None)

        size = path.stat().st_size
        with open(path, 'r') as f:
            if size > 50000:
                f.seek(size - 50000)
                f.readline()
            raw = f.read()

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
                    if (isinstance(block, dict)
                            and block.get('type') == 'tool_use'
                            and block.get('name') == 'Task'):
                        inp = block.get('input', {})
                        if inp.get('subagent_type', '').startswith('helix:helix-'):
                            prompt = inp.get('prompt', '')
                            if prompt:
                                last_prompt = prompt
            except (json.JSONDecodeError, AttributeError):
                continue

        if not last_prompt:
            return ParsedTranscript(None, False, None, None)

        has_insights = INSIGHTS_HEADER in last_prompt

        objective = None
        match = re.search(r'OBJECTIVE:\s*(.+?)(?:\n[A-Z_]+:|$)', last_prompt, re.DOTALL)
        if match:
            objective = match.group(1).strip()[:1000]

        constraints = None
        risk_areas = None
        c_match = re.search(r'CONSTRAINTS:\s*\n((?:- .+\n?)+)', last_prompt)
        if c_match:
            constraints = c_match.group(1).strip()[:2000]
        r_match = re.search(r'RISK_AREAS:\s*\n((?:- .+\n?)+)', last_prompt)
        if r_match:
            risk_areas = r_match.group(1).strip()[:2000]

        return ParsedTranscript(objective, has_insights, constraints, risk_areas)

    except Exception as e:
        _log_error("_parse_parent_transcript", e)
        return ParsedTranscript(None, False, None, None)


def _write_sideband(agent_id: str, names: List[str], objective: str = None,
                     query_embedding: str = None, constraints: str = None,
                     risk_areas: str = None):
    """Write sideband file for SubagentStop feedback attribution."""
    try:
        injected_dir = get_helix_dir() / "injected"
        injected_dir.mkdir(exist_ok=True)
        sideband_file = injected_dir / f"{agent_id}.json"
        data = {"names": names}
        if objective:
            data["objective"] = objective
        if query_embedding:
            data["query_embedding"] = query_embedding
        if constraints:
            data["constraints"] = constraints
        if risk_areas:
            data["risk_areas"] = risk_areas
        sideband_file.write_text(json.dumps(data))
    except Exception as e:
        _log_error("_write_sideband", e)


def _format_additional_context(memories: list, total_insights: int = 0) -> dict:
    """Format recalled insights as additionalContext for the agent."""
    if not memories:
        if total_insights > 0:
            return {"additionalContext": NO_MATCHING_MEMORY}
        return {"additionalContext": NO_PRIOR_MEMORY}

    insight_lines, names = format_insights(memories)
    lines = [INSIGHTS_HEADER] + [f"  - {line}" for line in insight_lines]
    if names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(names)}")
    return {"additionalContext": "\n".join(lines)}


def _collect_already_injected() -> list:
    """Read names from existing sideband files for cross-agent diversity."""
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


def process_hook_input(hook_input: dict) -> dict:
    """Process SubagentStart hook input."""
    agent_type = hook_input.get("agent_type", "")
    if not agent_type.startswith("helix:helix-"):
        return {}

    agent_id = hook_input.get("agent_id", "")
    transcript_path = hook_input.get("transcript_path", "")
    if not agent_id:
        return {}

    parsed = _parse_parent_transcript(transcript_path) if transcript_path else ParsedTranscript(None, False, None, None)
    objective = parsed.objective
    already_injected = parsed.has_insights
    if not objective:
        _log_injection(agent_id, agent_type, 0, False, True)
        return {"additionalContext": NO_PRIOR_MEMORY}
    if already_injected:
        _log_injection(agent_id, agent_type, 0, False, False)
        return {}

    suppress_names = _collect_already_injected()

    total_insights = 0
    try:
        from memory.core import recall
        memories = recall(objective, limit=3, suppress_names=suppress_names or None)
        if not memories:
            from memory.core import count
            total_insights = count()
    except Exception as e:
        _log_error("recall", e)
        memories = []

    names = [m.get("name", "") for m in memories if m.get("name")]

    wrote_sideband = False
    if names:
        query_emb_b64 = None
        try:
            from memory.embeddings import embed, to_blob
            emb_tuple = embed(objective, is_query=True)
            if emb_tuple:
                query_emb_b64 = base64.b64encode(to_blob(emb_tuple)).decode('ascii')
        except Exception:
            pass
        _write_sideband(agent_id, names, objective=objective, query_embedding=query_emb_b64,
                        constraints=parsed.constraints, risk_areas=parsed.risk_areas)
        wrote_sideband = True

    result = _format_additional_context(memories, total_insights=total_insights)
    _log_injection(agent_id, agent_type, len(names), wrote_sideband, "additionalContext" in result)
    return result


if __name__ == "__main__":
    from common import run_hook
    run_hook(process_hook_input)
