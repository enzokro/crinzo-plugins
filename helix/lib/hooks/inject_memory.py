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

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from paths import get_helix_dir


def _log_error(context: str, error: Exception):
    """Log error to extraction.log for diagnostics."""
    try:
        log_file = get_helix_dir() / "extraction.log"
        ts = datetime.now(timezone.utc).isoformat()
        with open(log_file, 'a') as f:
            f.write(f"{ts} | ERROR | inject_memory.{context} | {type(error).__name__}: {error}\n")
    except Exception:
        pass


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


def _extract_objective(transcript_path: str) -> Optional[str]:
    """Extract objective from the most recent helix Task spawn in parent transcript.

    Reads last portion of parent transcript JSONL, finds the last Task tool_use
    targeting a helix agent, and extracts the OBJECTIVE field from its prompt.

    Falls back to first 500 chars of the prompt if no OBJECTIVE field found.
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return None

        # Read last 50KB to avoid loading huge transcripts
        size = path.stat().st_size
        with open(path, 'r') as f:
            if size > 50000:
                f.seek(size - 50000)
                f.readline()  # skip partial line
            raw = f.read()

        # Parse JSONL lines, collect Task tool_use prompts for helix agents
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
            return None

        # Extract OBJECTIVE field (stops at next uppercase FIELD: or end of string)
        match = re.search(r'OBJECTIVE:\s*(.+?)(?:\n[A-Z_]+:|$)', last_prompt, re.DOTALL)
        if match:
            return match.group(1).strip()[:1000]

        # Fallback: first 500 chars of prompt
        return last_prompt[:500].strip()

    except Exception as e:
        _log_error("_extract_objective", e)
        return None


def _prompt_has_insights(transcript_path: str) -> bool:
    """Check if the most recent Task spawn prompt already contains INSIGHTS.

    When the orchestrator uses batch_inject + format_prompt, the prompt
    will contain 'INSIGHTS (from past experience):'.
    """
    try:
        path = Path(transcript_path)
        if not path.exists():
            return False

        size = path.stat().st_size
        with open(path, 'r') as f:
            if size > 50000:
                f.seek(size - 50000)
                f.readline()
            raw = f.read()

        # Scan backwards for last Task tool_use targeting helix agent
        for line in reversed(raw.strip().splitlines()):
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
                        if inp.get('subagent_type', '').startswith('helix:helix-'):
                            prompt = inp.get('prompt', '')
                            return 'INSIGHTS (from past experience):' in prompt
            except (json.JSONDecodeError, AttributeError):
                continue

        return False
    except Exception as e:
        _log_error("_prompt_has_insights", e)
        return False


def _write_sideband(agent_id: str, names: List[str]):
    """Write sideband file for SubagentStop feedback attribution.

    File: .helix/injected/{agent_id}.json
    Content: {"names": [...], "ts": "..."}
    """
    try:
        injected_dir = get_helix_dir() / "injected"
        injected_dir.mkdir(exist_ok=True)
        sideband_file = injected_dir / f"{agent_id}.json"
        sideband_file.write_text(json.dumps({
            "names": names,
            "ts": datetime.now(timezone.utc).isoformat()
        }))
    except Exception as e:
        _log_error("_write_sideband", e)


def _format_additional_context(memories: list) -> dict:
    """Format recalled insights as additionalContext for the agent."""
    if not memories:
        return {"additionalContext": "NO_PRIOR_MEMORY: Novel domain. Your INSIGHT output is especially valuable."}

    lines = ["INSIGHTS (from past experience):"]
    names = []
    for m in memories:
        eff = m.get("_effectiveness", m.get("effectiveness", 0.5))
        eff_pct = int(eff * 100)
        content = m.get("content", "")
        if content:
            lines.append(f"  - [{eff_pct}%] {content}")
            name = m.get("name", "")
            if name:
                names.append(name)

    if names:
        lines.append("")
        lines.append(f"INJECTED: {json.dumps(names)}")

    return {"additionalContext": "\n".join(lines)}


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

    # Extract objective from parent transcript
    objective = _extract_objective(transcript_path) if transcript_path else None
    if not objective:
        _log_injection(agent_id, agent_type, 0, False, True)
        return {"additionalContext": "NO_PRIOR_MEMORY: Novel domain. Your INSIGHT output is especially valuable."}

    # Orchestrator-injected builders: transcript has authoritative INJECTED names.
    # Don't recall or write sideband — can't identify specific tool_use in parallel spawns.
    already_injected = _prompt_has_insights(transcript_path) if transcript_path else False
    if already_injected:
        _log_injection(agent_id, agent_type, 0, False, False)
        return {}

    # Recall relevant insights
    try:
        from memory.core import recall
        memories = recall(objective, limit=5)
    except Exception as e:
        _log_error("recall", e)
        memories = []

    names = [m.get("name", "") for m in memories if m.get("name")]

    # Write sideband file for SubagentStop feedback attribution
    wrote_sideband = False
    if names:
        _write_sideband(agent_id, names)
        wrote_sideband = True

    result = _format_additional_context(memories)
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
