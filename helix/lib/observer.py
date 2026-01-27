#!/usr/bin/env python3
"""Observer: Extracts learnings from agent outputs.

Watches agent results and produces candidate memories.
Orchestrator reviews candidates and decides final storage.

Philosophy: Code surfaces facts; orchestrator decides actions.
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from .memory import recall, store, feedback
    from .memory.embeddings import embed, cosine
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from memory import recall, store, feedback
    from memory.embeddings import embed, cosine


def observe_explorer(output: dict) -> List[dict]:
    """Extract facts from explorer findings.

    Args:
        output: Explorer JSON output with scope, focus, findings

    Returns:
        List of candidate memories (type=fact) for orchestrator review
    """
    candidates = []
    scope = output.get("scope", "")

    for finding in output.get("findings", []):
        relevance = finding.get("relevance", "").lower()

        # Only extract high-value findings
        if relevance not in ("high", "critical", "important"):
            continue

        file_path = finding.get("file", "")
        what = finding.get("what", "")

        if not file_path or not what:
            continue

        trigger = f"{file_path}: {what}"

        # Check if we already know this (semantic dedup)
        existing = recall(trigger, type="fact", limit=1)
        if existing and existing[0].get("_relevance", 0) > 0.85:
            continue  # Already known

        candidates.append({
            "type": "fact",
            "trigger": trigger,
            "resolution": finding.get("context", what),
            "source": f"explorer:{scope}",
            "_confidence": "high" if relevance == "critical" else "medium"
        })

    # Extract framework detection as fact
    framework = output.get("framework", {})
    if framework.get("confidence") in ("HIGH", "MEDIUM"):
        candidates.append({
            "type": "fact",
            "trigger": f"Framework: {framework.get('detected', 'unknown')}",
            "resolution": f"Evidence: {framework.get('evidence', '')}",
            "source": f"explorer:{scope}",
            "_confidence": framework.get("confidence", "MEDIUM").lower()
        })

    # Extract patterns observed
    for pattern in output.get("patterns_observed", []):
        if len(pattern) > 15:  # Skip trivial patterns
            candidates.append({
                "type": "convention",
                "trigger": f"Pattern observed: {pattern}",
                "resolution": f"Found in {scope}",
                "source": f"explorer:{scope}",
                "_confidence": "low"  # Needs validation through use
            })

    return candidates


def observe_planner(tasks: List[dict], exploration: dict) -> List[dict]:
    """Extract decisions from planner output.

    Args:
        tasks: List of created tasks with subject, description, metadata
        exploration: The exploration data planner received

    Returns:
        List of candidate memories (type=decision) for orchestrator review
    """
    candidates = []

    # Decision indicators in text
    decision_patterns = [
        (r"chose?\s+(\w+)\s+(?:over|instead of)\s+(\w+)", "chose {0} over {1}"),
        (r"using\s+(\w+)\s+because\s+(.+?)(?:\.|$)", "using {0}: {1}"),
        (r"decided\s+to\s+(.+?)(?:\.|$)", "decision: {0}"),
        (r"approach:\s*(\w+)", "approach: {0}"),
        (r"strategy:\s*(.+?)(?:\.|$)", "strategy: {0}"),
    ]

    all_text = ""
    for task in tasks:
        all_text += f" {task.get('description', '')} {task.get('subject', '')}"
        notes = task.get("metadata", {}).get("notes", "")
        if notes:
            all_text += f" {notes}"

    for pattern, template in decision_patterns:
        for match in re.finditer(pattern, all_text, re.IGNORECASE):
            groups = match.groups()
            trigger = template.format(*groups) if groups else match.group(0)

            # Check if we already have this decision
            existing = recall(trigger, type="decision", limit=1)
            if existing and existing[0].get("_relevance", 0) > 0.8:
                continue

            candidates.append({
                "type": "decision",
                "trigger": trigger[:200],  # Cap length
                "resolution": f"Made during planning for {len(tasks)} tasks",
                "source": "planner",
                "_confidence": "medium"
            })

    return candidates


def observe_builder(
    task: dict,
    result: dict,
    files_changed: Optional[List[str]] = None
) -> List[dict]:
    """Extract conventions and evolution from builder work.

    Args:
        task: Task data (subject, description, metadata)
        result: Builder output with status, summary
        files_changed: List of files modified (from git diff --name-only).
                       If None, attempts to extract from task metadata.

    Returns:
        List of candidate memories for orchestrator review
    """
    candidates = []
    metadata = task.get("metadata", {})

    # Prefer files_changed from task metadata if available
    files_changed = files_changed or metadata.get("files_changed", [])

    # Extract verification info for richer evolution context
    verify_passed = metadata.get("verify_passed")
    verify_command = metadata.get("verify_command", "")

    status = result.get("status", "").lower()
    summary = result.get("summary", "")
    task_subject = task.get("subject", "")

    # Always create evolution entry for delivered tasks
    if status == "delivered" and files_changed:
        resolution_parts = [f"Changed: {', '.join(files_changed[:5])}{'...' if len(files_changed) > 5 else ''}"]
        if verify_command:
            resolution_parts.append(f"Verified: {verify_command}")
        if summary:
            resolution_parts.append(summary[:100])

        candidates.append({
            "type": "evolution",
            "trigger": f"Task: {task_subject}",
            "resolution": ". ".join(resolution_parts),
            "source": f"builder:{task.get('id', '')}",
            "_confidence": "high"  # We know this happened
        })

    # Extract conventions from successful implementations
    if status == "delivered":
        # Look for pattern indicators in the summary or task
        convention_indicators = [
            r"following\s+(.+?)\s+pattern",
            r"using\s+(.+?)\s+approach",
            r"implemented\s+with\s+(.+)",
            r"added\s+(.+?)\s+to\s+handle",
        ]

        text = f"{summary} {task.get('description', '')}"
        for pattern in convention_indicators:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                convention = match.group(1).strip()
                if len(convention) > 10 and len(convention) < 100:
                    candidates.append({
                        "type": "convention",
                        "trigger": f"Convention: {convention}",
                        "resolution": f"Applied in {task_subject}",
                        "source": f"builder:{task.get('id', '')}",
                        "_confidence": "low"  # Needs validation
                    })

    # Keep existing failure extraction (but now explicitly typed)
    if status == "blocked":
        error = result.get("error", "")
        tried = result.get("tried", "")

        if error and len(error) > 20:
            candidates.append({
                "type": "failure",
                "trigger": f"Error: {error[:150]}",
                "resolution": f"Tried: {tried[:150]}" if tried else "Investigation needed",
                "source": f"builder:{task.get('id', '')}",
                "_confidence": "high"  # We know this failed
            })

    return candidates


def observe_session(
    objective: str,
    tasks: List[dict],
    outcomes: Dict[str, str]
) -> dict:
    """Create session summary as evolution entry.

    Args:
        objective: Original user objective
        tasks: All tasks from the session
        outcomes: Dict mapping task_id -> helix_outcome (delivered/blocked/skipped)

    Returns:
        Single evolution memory candidate
    """
    delivered = [t for t in tasks if outcomes.get(t.get("id")) == "delivered"]
    blocked = [t for t in tasks if outcomes.get(t.get("id")) == "blocked"]

    # Summarize what was accomplished
    delivered_slugs = [t.get("subject", "").split(":", 1)[-1].strip()[:30] for t in delivered[:5]]

    summary_parts = [f"Completed {len(delivered)}/{len(tasks)} tasks"]
    if delivered_slugs:
        summary_parts.append(f"Delivered: {', '.join(delivered_slugs)}")
    if blocked:
        summary_parts.append(f"Blocked: {len(blocked)}")

    return {
        "type": "evolution",
        "trigger": f"Session: {objective[:80]}",
        "resolution": ". ".join(summary_parts),
        "source": "session-summary",
        "_confidence": "high"
    }


def should_store(candidate: dict, min_confidence: str = "medium") -> bool:
    """Decide if candidate meets storage threshold.

    Confidence levels: high > medium > low

    Args:
        candidate: Memory candidate with _confidence field
        min_confidence: Minimum confidence to store

    Returns:
        True if candidate should be stored
    """
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    candidate_conf = confidence_order.get(candidate.get("_confidence", "low"), 1)
    threshold_conf = confidence_order.get(min_confidence, 2)
    return candidate_conf >= threshold_conf


def store_candidates(
    candidates: List[dict],
    min_confidence: str = "medium"
) -> dict:
    """Store candidates that meet threshold.

    Args:
        candidates: List of memory candidates from observe_* functions
        min_confidence: Minimum confidence to store ("high", "medium", "low")

    Returns:
        Summary of storage operations
    """
    stored = []
    skipped = []

    for c in candidates:
        if not should_store(c, min_confidence):
            skipped.append({"trigger": c["trigger"][:50], "reason": "below_threshold"})
            continue

        # Remove internal fields before storing
        mem = {k: v for k, v in c.items() if not k.startswith("_")}
        result = store(**mem)

        if result.get("status") == "added":
            stored.append({"name": result["name"], "type": mem["type"]})
        elif result.get("status") == "merged":
            skipped.append({"trigger": c["trigger"][:50], "reason": "duplicate"})
        else:
            skipped.append({"trigger": c["trigger"][:50], "reason": result.get("reason", "unknown")})

    return {"stored": stored, "skipped": skipped}


# CLI for orchestrator usage
def _cli():
    import argparse

    parser = argparse.ArgumentParser(description="Observe agent outputs and extract learnings")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # observe-explorer
    p = subparsers.add_parser("explorer", help="Extract facts from explorer output")
    p.add_argument("--output", required=True, help="Explorer JSON output")
    p.add_argument("--store", action="store_true", help="Store candidates (not just return them)")
    p.add_argument("--min-confidence", default="medium", choices=["high", "medium", "low"])

    # observe-planner
    p = subparsers.add_parser("planner", help="Extract decisions from planner output")
    p.add_argument("--tasks", required=True, help="JSON list of created tasks")
    p.add_argument("--exploration", default="{}", help="JSON exploration data")
    p.add_argument("--store", action="store_true")
    p.add_argument("--min-confidence", default="medium", choices=["high", "medium", "low"])

    # observe-builder
    p = subparsers.add_parser("builder", help="Extract evolution/conventions from builder output")
    p.add_argument("--task", required=True, help="JSON task data")
    p.add_argument("--result", required=True, help="JSON builder result")
    p.add_argument("--files-changed", default="[]", help="JSON list of changed files")
    p.add_argument("--store", action="store_true")
    p.add_argument("--min-confidence", default="low", choices=["high", "medium", "low"])  # Lower default for builder

    # observe-session
    p = subparsers.add_parser("session", help="Create session summary")
    p.add_argument("--objective", required=True)
    p.add_argument("--tasks", required=True, help="JSON list of all tasks")
    p.add_argument("--outcomes", required=True, help="JSON dict of task_id -> outcome")
    p.add_argument("--store", action="store_true")

    args = parser.parse_args()

    if args.command == "explorer":
        output = json.loads(args.output)
        candidates = observe_explorer(output)
        if args.store:
            result = store_candidates(candidates, args.min_confidence)
            print(json.dumps({"candidates": candidates, "storage": result}, indent=2))
        else:
            print(json.dumps(candidates, indent=2))

    elif args.command == "planner":
        tasks = json.loads(args.tasks)
        exploration = json.loads(args.exploration)
        candidates = observe_planner(tasks, exploration)
        if args.store:
            result = store_candidates(candidates, args.min_confidence)
            print(json.dumps({"candidates": candidates, "storage": result}, indent=2))
        else:
            print(json.dumps(candidates, indent=2))

    elif args.command == "builder":
        task = json.loads(args.task)
        result_data = json.loads(args.result)
        files = json.loads(args.files_changed) if args.files_changed != "[]" else None
        candidates = observe_builder(task, result_data, files)
        if args.store:
            storage = store_candidates(candidates, args.min_confidence)
            print(json.dumps({"candidates": candidates, "storage": storage}, indent=2))
        else:
            print(json.dumps(candidates, indent=2))

    elif args.command == "session":
        tasks = json.loads(args.tasks)
        outcomes = json.loads(args.outcomes)
        candidate = observe_session(args.objective, tasks, outcomes)
        if args.store:
            result = store(
                trigger=candidate["trigger"],
                resolution=candidate["resolution"],
                type=candidate["type"],
                source=candidate["source"]
            )
            print(json.dumps({"candidate": candidate, "storage": result}, indent=2))
        else:
            print(json.dumps(candidate, indent=2))


if __name__ == "__main__":
    _cli()
