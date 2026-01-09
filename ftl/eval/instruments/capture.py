#!/usr/bin/env python3
"""Capture evidence from FTL evaluation runs.

Usage:
    python3 capture.py results/anki-v12
    python3 capture.py results/anki-v12 --output evidence/runs/anki-v12

Produces:
    - metrics.json: Quantitative data (agent counts, tokens, cache hits)
    - transcript.md: Readable narrative of what happened
"""

import json
import sys
import os
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime


def classify_agent(first_user_msg: str, model: str = "unknown", first_reads: list = None, tool_count: int = 0, tools: dict = None) -> str:
    """Classify agent by first user message, model, first file reads, and tool usage.

    Types:
    - planner: Reads spec/README, outputs task breakdown
    - router: Reads context files, creates workspace
    - builder: Reads workspace, writes code, runs verify
    - synthesizer: Reads completed workspaces, extracts patterns
    - direct: Single tool call, verification task (no workspace)
    - learner: Single task pattern extraction
    - warmup: Setup/initialization
    """
    first_reads = first_reads or []
    tools = tools or {}

    if not first_user_msg:
        return "unknown"
    msg = first_user_msg.lower()

    if msg.startswith("warmup"):
        return "warmup"
    if msg.startswith("objective:"):
        return "planner"

    # Planner detection: "## Prior Knowledge" header followed by "Objective:" somewhere in message
    # This catches planners that receive prior knowledge injection before the objective
    if msg.startswith("## prior knowledge") and "objective:" in msg:
        return "planner"

    # Planner detection: Contains task breakdown table (| Task | Slug | ... |)
    # This is a strong signal regardless of message prefix
    if "| task |" in msg and "| slug |" in msg:
        return "planner"

    # Direct execution detection: Single Bash tool call for verification
    # This catches verification tasks that skip workspace creation
    if tool_count == 1 and tools.get("Bash", 0) == 1:
        # Check if this looks like a verification task
        if "verify" in msg or "test" in msg or "pass" in msg[:500]:
            return "direct"

    # Synthesizer detection: campaign complete context or meta-pattern extraction
    if msg.startswith("synthesize") or "campaign completed" in msg:
        return "synthesizer"
    if "status: complete" in msg[:500] and "campaign:" in msg:
        return "synthesizer"
    if "extract cross-task" in msg or "meta-patterns" in msg[:500]:
        return "synthesizer"

    # Planner detection: Reads project files and outputs PROCEED or task breakdown
    # First "synthesizer" in v32 was actually a planner
    if any(r in ["README.md", "spec.md", "pyproject.toml"] for r in first_reads[:4]):
        if "confidence:" in msg or "proceed" in msg[:500] or "### tasks" in msg:
            return "planner"

    # Builder detection FIRST: workspace file with _active in prompt prefix
    # Must come before router check because builder prompts contain Campaign:/Task: context
    if msg.startswith("workspace:") and "_active" in msg[:600]:
        return "builder"

    # Learner detection: workspace with _complete (single task pattern extraction)
    if "workspace:" in msg or ".ftl/workspace/" in msg:
        if "_complete" in msg[:600] and "extract" not in msg[:200]:
            return "learner"

    # Router detection: Campaign context in prompt (but NOT workspace prefix)
    if "campaign:" in msg and "task:" in msg[:300]:
        return "router"

    # Router detection: Reads cache files first (session_context.md + workspace_state.md)
    # This is the definitive router signal regardless of model
    if len(first_reads) >= 2:
        first_two = [r.lower() for r in first_reads[:2]]
        if any("session_context" in r for r in first_two) and any("workspace_state" in r for r in first_two):
            return "router"
        # Also catch single cache file read as strong router signal
        if first_reads[0].lower() in ["session_context.md", "workspace_state.md"]:
            return "router"

    # Router detection: Cache content injected inline in prompt (starts with # Session Context)
    if msg.startswith("# session context") or msg.startswith("# workspace state"):
        return "router"

    return "unknown"


def parse_agent(filepath: Path) -> dict:
    """Parse single agent log file."""
    result = {
        "file": filepath.name,
        "type": "unknown",
        "model": "unknown",
        "tokens": {
            "input": 0,
            "cache_read": 0,
            "cache_create": 0,
            "output": 0,
            "total": 0,
        },
        "api_calls": 0,
        "tools": defaultdict(int),
        "tool_calls": 0,
        "first_reads": [],
        "cache_hit": False,
        "cache_had_content": False,  # NEW: did cache files have actual content?
        "errors": [],
        "messages": [],  # For transcript
        # NEW: structural data
        "task_id": None,
        "tool_sequence": [],
        "reasoning_trace": [],  # [{thinking: str, then: str|None}, ...]
        "first_user_full": "",
        "file_mtime": filepath.stat().st_mtime,
        # NEW: loop stability signals
        "task_outcome": None,  # "complete" | "failed" | None
        "used_fallback": False,  # True if reasoning mentions fallback/not available
    }

    first_user = None
    read_calls = []
    bash_commands = []
    model = "unknown"
    pending_tool_id = None  # Track tool_use id for result matching
    pending_tool_name = None
    cache_file_reads = {}  # {tool_id: filename} for cache file reads

    with open(filepath, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            # Extract first user message (full, no truncation)
            if first_user is None and entry.get("type") == "user":
                content = entry.get("message", {}).get("content", [])
                if isinstance(content, str):
                    first_user = content
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            first_user = block.get("text", "")
                            break

            # Extract assistant info
            if entry.get("type") == "assistant":
                msg = entry.get("message", {})

                # Model
                if msg.get("model") and model == "unknown":
                    model = msg["model"]
                    result["model"] = model

                # Tokens
                usage = msg.get("usage", {})
                if usage:
                    result["api_calls"] += 1
                    result["tokens"]["input"] += usage.get("input_tokens", 0)
                    result["tokens"]["cache_read"] += usage.get("cache_read_input_tokens", 0)
                    result["tokens"]["cache_create"] += usage.get("cache_creation_input_tokens", 0)
                    result["tokens"]["output"] += usage.get("output_tokens", 0)

                # Tool calls and responses for transcript
                content = msg.get("content", [])
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                result["tools"][tool_name] += 1
                                result["tool_calls"] += 1
                                result["tool_sequence"].append(tool_name)

                                tool_input = block.get("input", {})
                                result["messages"].append({
                                    "type": "tool_call",
                                    "tool": tool_name,
                                    "input": summarize_tool_input(tool_name, tool_input)
                                })

                                # Link to previous reasoning in trace
                                if result["reasoning_trace"] and result["reasoning_trace"][-1]["then"] is None:
                                    result["reasoning_trace"][-1]["then"] = tool_name

                                if tool_name == "Read":
                                    fp = tool_input.get("file_path", "")
                                    filename = fp.split("/")[-1] if fp else "unknown"
                                    read_calls.append(filename)
                                    # Track cache file reads for content verification
                                    tool_id = block.get("id")
                                    if tool_id and ("context" in filename.lower() or "state" in filename.lower()):
                                        cache_file_reads[tool_id] = filename
                                elif tool_name == "Bash":
                                    cmd = tool_input.get("command", "")
                                    bash_commands.append(cmd)  # Keep full for outcome detection

                            elif block.get("type") == "text":
                                text = block.get("text", "")
                                if text.strip() and len(text.strip()) > 20:
                                    # Add to reasoning trace (thinking -> action)
                                    result["reasoning_trace"].append({
                                        "thinking": text.strip()[:400],
                                        "then": None  # Will be filled by next tool_use
                                    })
                                    result["messages"].append({
                                        "type": "assistant_text",
                                        "text": text[:500]
                                    })

            # Track tool results - check if cache reads returned content
            if entry.get("type") == "tool_result":
                tool_id = entry.get("tool_use_id")
                if tool_id and tool_id in cache_file_reads:
                    # Check if the cache file had actual content
                    content = entry.get("content", "")
                    if isinstance(content, list):
                        content = " ".join(
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        )
                    # Cache has content if it's more than just line numbers/empty
                    # Real content has meaningful text beyond "1→\n2→\n"
                    content_lines = [l for l in content.split("\n") if l.strip() and not re.match(r'^\s*\d+→\s*$', l)]
                    if len(content_lines) > 2:  # More than just header lines
                        result["cache_had_content"] = True

            # Track errors
            if entry.get("type") == "error":
                result["errors"].append(entry.get("message", "unknown error"))

    result["type"] = classify_agent(
        first_user or "",
        model,
        read_calls,
        tool_count=result["tool_calls"],
        tools=result["tools"]
    )
    result["tokens"]["total"] = sum(result["tokens"].values())
    result["first_reads"] = read_calls[:10]
    result["tools"] = dict(result["tools"])
    result["first_user_full"] = first_user or ""

    # Extract task_id from prompt content (not first_reads - those are context, not assignment)
    task_id = None
    if first_user:
        # Router: "Task: NNN name" or "Task: NNN"
        match = re.search(r'Task:\s*(\d{3})', first_user)
        if match:
            task_id = match.group(1)
        # Builder: "Workspace:...NNN_name_active"
        if not task_id:
            match = re.search(r'Workspace:[^\n]*?(\d{3})_', first_user)
            if match:
                task_id = match.group(1)
    result["task_id"] = task_id

    # Cache hit detection - did router READ cache files?
    result["cache_hit"] = any(
        "context" in r.lower() or "state" in r.lower()
        for r in read_calls[:2]
    )
    # Note: cache_had_content (set above) tells if those files had actual content

    # Task outcome detection - look for workspace rename commands (use full commands before truncation)
    for cmd in bash_commands:
        if "mv " in cmd and ".ftl/workspace/" in cmd:
            if "_complete" in cmd:
                result["task_outcome"] = "complete"
                break
            elif "_failed" in cmd:
                result["task_outcome"] = "failed"
                break

    # Store truncated commands for metrics output
    result["bash_commands"] = [cmd[:100] for cmd in bash_commands[:10]]

    # Fallback detection - scan reasoning for environmental limitations
    fallback_indicators = [
        "not available",
        "fallback",
        "manually",
        "library scripts are not",
        "doesn't exist",
        "no cache",
        "environment",
    ]
    for entry in result["reasoning_trace"]:
        thinking = entry.get("thinking", "").lower()
        # Only flag substantive fallbacks, not routine "no cache" at start
        if any(ind in thinking for ind in ["not available", "fallback", "manually", "library scripts"]):
            result["used_fallback"] = True
            break

    return result


def summarize_tool_input(tool_name: str, tool_input: dict) -> str:
    """Create readable summary of tool input."""
    if tool_name == "Read":
        path = tool_input.get("file_path", "")
        return path.split("/")[-1] if path else "unknown file"
    elif tool_name == "Write":
        path = tool_input.get("file_path", "")
        return f"write to {path.split('/')[-1] if path else 'unknown'}"
    elif tool_name == "Edit":
        path = tool_input.get("file_path", "")
        return f"edit {path.split('/')[-1] if path else 'unknown'}"
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "")[:80]
        return cmd
    elif tool_name == "Task":
        desc = tool_input.get("description", "")[:50]
        agent = tool_input.get("subagent_type", "unknown")
        return f"spawn {agent}: {desc}"
    elif tool_name == "Glob":
        pattern = tool_input.get("pattern", "")
        return f"glob {pattern}"
    elif tool_name == "Grep":
        pattern = tool_input.get("pattern", "")[:40]
        return f"grep {pattern}"
    else:
        return str(tool_input)[:80]


def parse_main_session(run_dir: Path) -> dict:
    """Parse main orchestrator session for spawn chain.

    Returns: {
        "session_id": "f5309c4c-...",
        "spawns": [
            {"order": 0, "type": "planner", "task": None, "description": "..."},
            {"order": 1, "type": "router", "task": "001", "description": "..."},
            ...
        ],
        "total_spawns": 14
    }
    """
    # Find non-agent JSONL file
    main_files = [f for f in run_dir.glob("*.jsonl") if not f.name.startswith("agent-")]
    if not main_files:
        return {"session_id": None, "spawns": [], "total_spawns": 0}

    main_file = main_files[0]  # Should be exactly one
    session_id = main_file.stem

    spawns = []
    spawn_order = 0

    with open(main_file, "r") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if entry.get("type") != "assistant":
                continue

            content = entry.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue

            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "Task":
                    inp = block.get("input", {})
                    subagent = inp.get("subagent_type", "unknown")
                    desc = inp.get("description", "")[:80]

                    # Extract task number from description if present
                    task_match = re.search(r"task\s*(\d{3})", desc.lower())
                    task_id = task_match.group(1) if task_match else None

                    # Map subagent_type to classification
                    type_map = {
                        "ftl:ftl-router": "router",
                        "ftl:ftl-builder": "builder",
                        "ftl:ftl-planner": "planner",
                        "ftl:ftl-synthesizer": "synthesizer",
                        "ftl:ftl-learner": "learner",
                    }
                    agent_type = type_map.get(subagent, subagent)

                    spawns.append({
                        "order": spawn_order,
                        "type": agent_type,
                        "task": task_id,
                        "description": desc,
                        "subagent_type": subagent,
                    })
                    spawn_order += 1

    return {
        "session_id": session_id,
        "spawns": spawns,
        "total_spawns": len(spawns),
    }


def build_spawn_graph_from_main(main_session: dict, agents: list) -> tuple:
    """Build spawn graph by matching spawn intent to agent execution via task_id.

    Returns: (spawn_graph dict, updated agents with spawn_order)
    """
    spawns = main_session.get("spawns", [])
    if not spawns:
        return {}, agents

    spawn_graph = {"orchestrator": []}

    # Track unmatched agents by type for fallback matching
    unmatched_by_type = {}
    for agent in agents:
        atype = agent["type"]
        if atype not in unmatched_by_type:
            unmatched_by_type[atype] = []
        unmatched_by_type[atype].append(agent)

    # Index agents by (type, task_id) for exact matching
    agent_index = {}
    for agent in agents:
        key = (agent["type"], agent.get("task_id"))
        if key not in agent_index:
            agent_index[key] = []
        agent_index[key].append(agent)

    matched_agents = set()

    # Match spawns to agents
    for spawn in spawns:
        stype = spawn["type"]
        stask = spawn.get("task")

        agent = None

        # Try exact match by (type, task)
        key = (stype, stask)
        candidates = agent_index.get(key, [])
        for c in candidates:
            if c["file"] not in matched_agents:
                agent = c
                break

        # Fallback: match any unmatched agent of same type
        if not agent:
            for c in unmatched_by_type.get(stype, []):
                if c["file"] not in matched_agents:
                    agent = c
                    break

        if agent:
            matched_agents.add(agent["file"])
            agent["spawn_order"] = spawn["order"]
            # Trust spawn's task as authoritative
            if stask:
                agent["task_id"] = stask
            agent_id = f"{agent['type']}-{agent['file'][6:13]}"
            spawn_graph["orchestrator"].append(agent_id)

    return spawn_graph, agents


def extract_metrics(run_dir: Path) -> dict:
    """Extract quantitative metrics from run directory."""
    metrics = {
        "run_id": run_dir.name,
        "captured_at": datetime.now().isoformat(),
        "agents": [],
        "by_type": {},
        "totals": {
            "tokens": 0,
            "tokens_by_category": {"input": 0, "cache_read": 0, "cache_create": 0, "output": 0},
            "api_calls": 0,
            "tool_calls": 0,
            "agents": 0,
        },
        "cache_efficiency": 0.0,
        "protocol_fidelity": {},
    }

    type_data = defaultdict(lambda: {
        "count": 0,
        "tokens": 0,
        "cache_hits": 0,
        "models": defaultdict(int),
    })

    agents = []
    for filepath in sorted(run_dir.glob("agent-*.jsonl")):
        agent = parse_agent(filepath)

        # Skip warmup and tiny logs
        if agent["tokens"]["total"] < 1000 or agent["type"] == "warmup":
            continue

        agents.append(agent)
        atype = agent["type"]

        # Aggregate by type
        type_data[atype]["count"] += 1
        type_data[atype]["tokens"] += agent["tokens"]["total"]
        if agent["cache_hit"]:
            type_data[atype]["cache_hits"] += 1
        type_data[atype]["models"][agent["model"]] += 1

        # Totals
        metrics["totals"]["tokens"] += agent["tokens"]["total"]
        metrics["totals"]["api_calls"] += agent["api_calls"]
        metrics["totals"]["tool_calls"] += agent["tool_calls"]
        metrics["totals"]["agents"] += 1
        for cat in ["input", "cache_read", "cache_create", "output"]:
            metrics["totals"]["tokens_by_category"][cat] += agent["tokens"][cat]

    # Finalize by_type
    for atype, data in type_data.items():
        data["models"] = dict(data["models"])
    metrics["by_type"] = {k: dict(v) for k, v in type_data.items()}

    # Cache efficiency
    total = metrics["totals"]["tokens"]
    cache_read = metrics["totals"]["tokens_by_category"]["cache_read"]
    metrics["cache_efficiency"] = cache_read / total if total > 0 else 0

    # Protocol fidelity observations
    learner_count = type_data.get("learner", {}).get("count", 0)
    planner_count = type_data.get("planner", {}).get("count", 0)
    synth_count = type_data.get("synthesizer", {}).get("count", 0)
    router_count = type_data.get("router", {}).get("count", 0)
    builder_count = type_data.get("builder", {}).get("count", 0)

    # Count routers with actual cache content (not just cache file reads)
    routers_with_cache_content = sum(
        1 for a in agents
        if a["type"] == "router" and a.get("cache_had_content", False)
    )

    # Count fallback usage
    fallback_count = sum(1 for a in agents if a.get("used_fallback", False))

    # Count task outcomes
    complete_count = sum(1 for a in agents if a.get("task_outcome") == "complete")
    failed_count = sum(1 for a in agents if a.get("task_outcome") == "failed")

    metrics["protocol_fidelity"] = {
        "no_learners": learner_count == 0,
        "single_planner": planner_count == 1,
        "single_synthesizer": synth_count == 1,
        "router_builder_match": router_count == builder_count,
        "router_cache_rate": type_data.get("router", {}).get("cache_hits", 0) / router_count if router_count > 0 else 0,
        # NEW: actual cache effectiveness (content present, not just file read)
        "router_cache_effective": routers_with_cache_content / router_count if router_count > 0 else 0,
    }

    # NEW: loop stability signals
    metrics["loop_signals"] = {
        "tasks_complete": complete_count,
        "tasks_failed": failed_count,
        "fallback_used": fallback_count,
        "agents_with_fallback": [a["file"] for a in agents if a.get("used_fallback", False)],
    }

    # Parse main session for spawn chain (authoritative source)
    main_session = parse_main_session(run_dir)
    metrics["main_session"] = {
        "session_id": main_session["session_id"],
        "total_spawns": main_session["total_spawns"],
    }

    # Build spawn graph from main session
    spawn_graph, agents = build_spawn_graph_from_main(main_session, agents)
    metrics["spawn_graph"] = spawn_graph

    # Include spawn sequence in metrics
    metrics["spawn_sequence"] = main_session["spawns"]

    # Build task flow summary
    task_agents = defaultdict(list)
    for agent in agents:
        if agent.get("task_id"):
            task_agents[agent["task_id"]].append(agent)

    task_flow = {}
    for task_id, task_list in sorted(task_agents.items()):
        routers = [a for a in task_list if a["type"] == "router"]
        builders = [a for a in task_list if a["type"] == "builder"]
        task_flow[task_id] = {
            "routers": len(routers),
            "builders": len(builders),
            "attempts": max(len(routers), 1),
            "tokens": sum(a["tokens"]["total"] for a in task_list),
        }
    metrics["task_flow"] = task_flow

    # Store agent summaries (without full messages for metrics)
    metrics["agents"] = [
        {k: v for k, v in a.items() if k != "messages"}
        for a in agents
    ]

    return metrics, agents


def generate_transcript(agents: list, run_id: str) -> str:
    """Generate readable transcript from agent data."""
    lines = [
        f"# Transcript: {run_id}",
        "",
        f"*Captured: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        "",
        "---",
        "",
    ]

    for i, agent in enumerate(agents, 1):
        task_str = f"task-{agent.get('task_id')}" if agent.get('task_id') else ""
        agent_label = f"{agent['type'].capitalize()} {task_str}".strip()
        lines.append(f"## {agent_label} ({agent['file'][:13]})")

        # Build status line with signals
        status_parts = [f"Model: {agent['model']}", f"Tokens: {agent['tokens']['total']:,}", f"Order: {agent.get('spawn_order', '?')}"]
        if agent.get("task_outcome"):
            outcome_emoji = "✓" if agent["task_outcome"] == "complete" else "✗"
            status_parts.append(f"Outcome: {outcome_emoji}")
        if agent.get("used_fallback"):
            status_parts.append("⚠️ fallback")
        lines.append(f"*{' | '.join(status_parts)}*")
        lines.append("")

        # Reasoning trace narrative
        reasoning_trace = agent.get("reasoning_trace", [])
        if reasoning_trace:
            for entry in reasoning_trace[:15]:  # Limit to first 15 entries
                thinking = entry.get("thinking", "")
                then = entry.get("then")

                # Show thinking (truncate long thoughts)
                if len(thinking) > 150:
                    thinking_display = thinking[:150] + "..."
                else:
                    thinking_display = thinking
                lines.append(f'💭 "{thinking_display}"')

                # Show action if present
                if then:
                    lines.append(f"⚡ {then}")
                lines.append("")

            if len(reasoning_trace) > 15:
                lines.append(f"*... {len(reasoning_trace) - 15} more reasoning steps*")
                lines.append("")
        else:
            # Fallback to tool sequence if no reasoning trace
            tool_summary = ", ".join(f"{t}×{c}" for t, c in sorted(agent["tools"].items(), key=lambda x: -x[1])[:5])
            lines.append(f"**Tools**: {tool_summary}")
            lines.append("")

        if agent.get("errors"):
            lines.append(f"**Errors**: {len(agent['errors'])}")
            for err in agent["errors"][:3]:
                lines.append(f"  - {err[:100]}")
            lines.append("")

        lines.append("---")
        lines.append("")

    # Summary section
    type_counts = defaultdict(int)
    total_tokens = 0
    complete_count = 0
    failed_count = 0
    fallback_count = 0
    cache_effective_count = 0
    router_count = 0

    for agent in agents:
        type_counts[agent["type"]] += 1
        total_tokens += agent["tokens"]["total"]
        if agent.get("task_outcome") == "complete":
            complete_count += 1
        elif agent.get("task_outcome") == "failed":
            failed_count += 1
        if agent.get("used_fallback"):
            fallback_count += 1
        if agent["type"] == "router":
            router_count += 1
            if agent.get("cache_had_content"):
                cache_effective_count += 1

    lines.append("## Summary")
    lines.append("")
    lines.append(f"**Total agents**: {len(agents)}")
    lines.append(f"**Total tokens**: {total_tokens:,}")
    lines.append("")

    # Loop signals section
    lines.append("**Loop Signals**:")
    lines.append(f"  - Tasks complete: {complete_count}")
    if failed_count > 0:
        lines.append(f"  - Tasks failed: {failed_count} ⚠️")
    if fallback_count > 0:
        lines.append(f"  - Agents with fallback: {fallback_count} ⚠️")
    cache_pct = (cache_effective_count / router_count * 100) if router_count > 0 else 0
    if router_count > 0:
        lines.append(f"  - Router cache effective: {cache_effective_count}/{router_count} ({cache_pct:.0f}%)")
    lines.append("")

    lines.append("**By type**:")
    for atype in ["planner", "router", "builder", "learner", "synthesizer", "unknown"]:
        if type_counts[atype] > 0:
            marker = " ⚠️" if atype == "learner" else ""
            lines.append(f"  - {atype}: {type_counts[atype]}{marker}")

    # Spawn sequence section (if main session captured)
    if any(a.get("spawn_order") is not None for a in agents):
        lines.append("")
        lines.append("## Spawn Sequence")
        lines.append("")
        sorted_by_spawn = sorted(
            [a for a in agents if a.get("spawn_order") is not None],
            key=lambda a: a["spawn_order"]
        )
        for agent in sorted_by_spawn:
            task_str = f"task {agent.get('task_id')}" if agent.get('task_id') else ""
            lines.append(f"{agent['spawn_order']:2d}. {agent['type']:12s} {task_str}")

    return "\n".join(lines)


def capture(run_dir: Path, output_dir: Path = None):
    """Main capture function."""
    if not run_dir.exists():
        print(f"Error: {run_dir} does not exist")
        sys.exit(1)

    # Default output location
    if output_dir is None:
        eval_dir = Path(__file__).parent.parent
        output_dir = eval_dir / "evidence" / "runs" / run_dir.name

    output_dir.mkdir(parents=True, exist_ok=True)

    # Extract metrics and agents
    metrics, agents = extract_metrics(run_dir)

    # Write metrics
    metrics_path = output_dir / "metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    print(f"Wrote: {metrics_path}")

    # Generate and write transcript
    transcript = generate_transcript(agents, run_dir.name)
    transcript_path = output_dir / "transcript.md"
    with open(transcript_path, "w") as f:
        f.write(transcript)
    print(f"Wrote: {transcript_path}")

    # Print quick summary
    print(f"\n{run_dir.name}: {metrics['totals']['agents']} agents, {metrics['totals']['tokens']:,} tokens")
    print(f"Cache efficiency: {metrics['cache_efficiency']:.1%}")

    fidelity = metrics["protocol_fidelity"]
    issues = []
    if not fidelity["no_learners"]:
        issues.append("learners present")
    if not fidelity["single_planner"]:
        issues.append("planner count wrong")
    if not fidelity["single_synthesizer"]:
        issues.append("synthesizer count wrong")
    if not fidelity["router_builder_match"]:
        issues.append("router/builder mismatch")

    if issues:
        print(f"Issues: {', '.join(issues)}")
    else:
        print("Protocol: OK")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 capture.py <results_dir> [--output <output_dir>] [--info-theory]")
        sys.exit(1)

    run_dir = Path(sys.argv[1])
    output_dir = None
    run_info_theory = "--info-theory" in sys.argv

    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_dir = Path(sys.argv[idx + 1])

    capture(run_dir, output_dir)

    # Run info theory analysis if requested
    if run_info_theory:
        from info_theory import analyze as analyze_info_theory
        # Use the output_dir for info_theory analysis
        evidence_path = output_dir if output_dir else Path(__file__).parent.parent / "evidence" / "runs" / run_dir.name
        print("\n--- Info Theory Analysis ---")
        analyze_info_theory(evidence_path)
