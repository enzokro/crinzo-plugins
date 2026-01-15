#!/usr/bin/env python3
"""Exploration aggregation and storage."""

from pathlib import Path
from datetime import datetime
import json
import argparse
import sys
import subprocess
import re


EXPLORATION_FILE = Path(".ftl/exploration.json")


def extract_json(text: str) -> dict | None:
    """Extract JSON from text that may contain extra content.

    Handles common LLM output issues:
    - Markdown code blocks (```json ... ```)
    - Text before/after JSON
    - Multiple JSON objects (takes first valid one)

    Args:
        text: Raw text that should contain JSON

    Returns:
        Parsed dict or None if no valid JSON found
    """
    text = text.strip()

    # Try direct parse first (fastest path)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Remove markdown code blocks
    # Match ```json ... ``` or ``` ... ```
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Find JSON object pattern (greedy match from first { to last })
    # This handles: "Here is JSON: {...}" or "{...}\n\nSome explanation"
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    # Try to find any { ... } pattern (more permissive)
    brace_start = text.find('{')
    brace_end = text.rfind('}')
    if brace_start != -1 and brace_end > brace_start:
        potential_json = text[brace_start:brace_end + 1]
        try:
            return json.loads(potential_json)
        except json.JSONDecodeError:
            pass

    return None


def validate_result(result: dict) -> tuple[bool, str]:
    """Validate an explorer result has required fields.

    Args:
        result: Explorer output dict

    Returns:
        (is_valid, error_message)
    """
    if not isinstance(result, dict):
        return False, "Result is not a dict"

    if "mode" not in result:
        return False, "Missing required field: mode"

    valid_modes = {"structure", "pattern", "memory", "delta"}
    if result["mode"] not in valid_modes:
        return False, f"Invalid mode: {result['mode']}"

    if "status" not in result:
        return False, "Missing required field: status"

    return True, ""


def aggregate(results: list[dict], objective: str = None) -> dict:
    """Combine explorer outputs into single exploration dict.

    Args:
        results: List of explorer output dicts (each has 'mode' key)
        objective: Original objective text

    Returns:
        Combined exploration dict with _meta and mode sections
    """
    # Get git sha if available
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        ).stdout.strip()
    except Exception:
        git_sha = "unknown"

    exploration = {
        "_meta": {
            "version": "1.0",
            "created_at": datetime.now().isoformat(),
            "git_sha": git_sha,
            "objective": objective,
        }
    }

    for r in results:
        is_valid, error = validate_result(r)
        if not is_valid:
            # Skip invalid results but continue processing
            continue

        mode = r["mode"]
        status = r.get("status", "unknown")

        if status in ["ok", "partial"]:
            exploration[mode] = r
        else:
            exploration[mode] = {
                "mode": mode,
                "status": "error",
                "_error": r.get("error", "unknown error")
            }

    return exploration


def write(exploration: dict) -> Path:
    """Write exploration.json to .ftl directory.

    Args:
        exploration: Aggregated exploration dict

    Returns:
        Path to written file
    """
    EXPLORATION_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXPLORATION_FILE.write_text(json.dumps(exploration, indent=2))
    return EXPLORATION_FILE


def read() -> dict | None:
    """Read exploration.json if exists.

    Returns:
        Exploration dict or None if file doesn't exist
    """
    if not EXPLORATION_FILE.exists():
        return None
    return json.loads(EXPLORATION_FILE.read_text())


def get_structure() -> dict:
    """Get structure section from exploration, with fallback.

    Returns:
        Structure dict or empty fallback
    """
    exploration = read()
    if not exploration:
        return {"status": "missing"}
    return exploration.get("structure", {"status": "missing"})


def get_pattern() -> dict:
    """Get pattern section from exploration, with fallback.

    Returns:
        Pattern dict or empty fallback
    """
    exploration = read()
    if not exploration:
        return {
            "status": "missing",
            "framework": "none",
            "idioms": {"required": [], "forbidden": []}
        }
    return exploration.get("pattern", {
        "status": "missing",
        "framework": "none",
        "idioms": {"required": [], "forbidden": []}
    })


def get_memory() -> dict:
    """Get memory section from exploration, with fallback.

    Returns:
        Memory dict or empty fallback
    """
    exploration = read()
    if not exploration:
        return {
            "status": "missing",
            "failures": [],
            "patterns": [],
            "total_in_memory": {"failures": 0, "patterns": 0}
        }
    return exploration.get("memory", {
        "status": "missing",
        "failures": [],
        "patterns": [],
        "total_in_memory": {"failures": 0, "patterns": 0}
    })


def get_delta() -> dict:
    """Get delta section from exploration, with fallback.

    Returns:
        Delta dict or empty fallback
    """
    exploration = read()
    if not exploration:
        return {"status": "missing", "candidates": []}
    return exploration.get("delta", {"status": "missing", "candidates": []})


def clear() -> bool:
    """Remove exploration.json if exists.

    Returns:
        True if file was removed, False if didn't exist
    """
    if EXPLORATION_FILE.exists():
        EXPLORATION_FILE.unlink()
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="FTL exploration operations")
    subparsers = parser.add_subparsers(dest="command")

    # aggregate command - reads JSON lines from stdin
    agg = subparsers.add_parser("aggregate", help="Aggregate explorer outputs")
    agg.add_argument("--objective", help="Original objective text")

    # write command - writes exploration dict from stdin
    w = subparsers.add_parser("write", help="Write exploration.json from stdin")

    # read command - read exploration.json
    subparsers.add_parser("read", help="Read exploration.json")

    # get commands for each section
    subparsers.add_parser("get-structure", help="Get structure section")
    subparsers.add_parser("get-pattern", help="Get pattern section")
    subparsers.add_parser("get-memory", help="Get memory section")
    subparsers.add_parser("get-delta", help="Get delta section")

    # clear command
    subparsers.add_parser("clear", help="Remove exploration.json")

    args = parser.parse_args()

    if args.command == "aggregate":
        # Read JSON objects from stdin (one per line)
        # Uses extract_json for robust parsing (handles markdown, extra text)
        results = []
        for line in sys.stdin:
            line = line.strip()
            if line:
                parsed = extract_json(line)
                if parsed is not None:
                    results.append(parsed)
                # Skip unparseable lines silently
        exploration = aggregate(results, args.objective)
        print(json.dumps(exploration, indent=2))

    elif args.command == "write":
        exploration = json.load(sys.stdin)
        path = write(exploration)
        print(f"Written: {path}")

    elif args.command == "read":
        exploration = read()
        if exploration:
            print(json.dumps(exploration, indent=2))
        else:
            print("null")

    elif args.command == "get-structure":
        print(json.dumps(get_structure(), indent=2))

    elif args.command == "get-pattern":
        print(json.dumps(get_pattern(), indent=2))

    elif args.command == "get-memory":
        print(json.dumps(get_memory(), indent=2))

    elif args.command == "get-delta":
        print(json.dumps(get_delta(), indent=2))

    elif args.command == "clear":
        removed = clear()
        if removed:
            print("Cleared: .ftl/exploration.json")
        else:
            print("No exploration.json to clear")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
