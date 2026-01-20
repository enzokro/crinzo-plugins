#!/usr/bin/env python3
"""Parse planner output for PROCEED/CLARIFY decision detection.

Implements machine-readable decision detection for SKILL.md state machine,
removing ambiguity in CLARIFY detection.
"""

import argparse
import json
import re
import sys
from pathlib import Path


# Decision markers to detect in planner output
CLARIFY_MARKERS = [
    r"^### CLARIFY",
    r"^## Blocking Questions",
    r"^Confidence:\s*CLARIFY",
    r"^Decision:\s*CLARIFY",
    r"CLARIFY.*need.*clarification",
]

PROCEED_MARKERS = [
    r"^### Confidence:\s*PROCEED",
    r"^Confidence:\s*PROCEED",
    r"^Decision:\s*PROCEED",
    r"```json\s*\{",  # JSON code block indicates plan output
]

CONFIRM_MARKERS = [
    r"^### Confidence:\s*CONFIRM",
    r"^Confidence:\s*CONFIRM",
    r"^Decision:\s*CONFIRM",
]


def detect_decision(text: str) -> dict:
    """Detect PROCEED/CLARIFY/CONFIRM decision from planner output.

    Args:
        text: Raw planner output text

    Returns:
        {
            "decision": "PROCEED" | "CLARIFY" | "CONFIRM" | "UNKNOWN",
            "markers_found": ["marker1", ...],
            "questions": [...] if CLARIFY,
            "plan_json": {...} if PROCEED,
            "validation": {"valid": bool, "errors": [...]} if plan present
        }
    """
    result = {
        "decision": "UNKNOWN",
        "markers_found": [],
    }

    lines = text.split("\n")

    # Check for CLARIFY markers first (higher priority)
    for pattern in CLARIFY_MARKERS:
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                result["markers_found"].append(pattern)
                result["decision"] = "CLARIFY"
                break
        if result["decision"] == "CLARIFY":
            break

    # If CLARIFY, extract questions
    if result["decision"] == "CLARIFY":
        questions = extract_questions(text)
        if questions:
            result["questions"] = questions
        return result

    # Check for CONFIRM markers
    for pattern in CONFIRM_MARKERS:
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                result["markers_found"].append(pattern)
                result["decision"] = "CONFIRM"
                return result

    # Check for PROCEED markers
    for pattern in PROCEED_MARKERS:
        for line in lines:
            if re.search(pattern, line, re.IGNORECASE | re.MULTILINE):
                result["markers_found"].append(pattern)
                result["decision"] = "PROCEED"
                break

    # Extract plan JSON if present
    plan_json = extract_plan_json(text)
    if plan_json:
        result["plan_json"] = plan_json
        # If no explicit marker but plan found, infer PROCEED
        if result["decision"] == "UNKNOWN":
            result["decision"] = "PROCEED"
            result["inferred"] = True  # Marker was missing, inferred from JSON

    # Always validate plan if present (unconditional validation)
    if result.get("plan_json"):
        result["validation"] = validate_plan(result["plan_json"])

    return result


def extract_questions(text: str) -> list:
    """Extract blocking questions from CLARIFY output.

    Args:
        text: Planner output with CLARIFY

    Returns:
        List of question strings
    """
    questions = []

    # Pattern 1: Numbered questions
    numbered = re.findall(r"^\d+\.\s*(.+\?)", text, re.MULTILINE)
    questions.extend(numbered)

    # Pattern 2: Questions after "Blocking Questions" header
    blocking_section = re.search(
        r"(?:Blocking Questions|Questions).*?(?=##|\Z)",
        text,
        re.IGNORECASE | re.DOTALL
    )
    if blocking_section:
        section_questions = re.findall(r"[-*]\s*(.+\?)", blocking_section.group())
        questions.extend(section_questions)

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for q in questions:
        q_clean = q.strip()
        if q_clean and q_clean not in seen:
            seen.add(q_clean)
            unique.append(q_clean)

    return unique


def extract_plan_json(text: str) -> dict | None:
    """Extract plan.json from planner output.

    Args:
        text: Planner output

    Returns:
        Parsed plan dict or None
    """
    # Pattern 1: JSON in code block
    json_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    # Pattern 2: Any JSON object containing objective and tasks (brace-balanced)
    if '"objective"' in text and '"tasks"' in text:
        # Find first { before "objective"
        obj_idx = text.find('"objective"')
        start = text.rfind('{', 0, obj_idx)
        if start != -1:
            depth = 0
            for i, c in enumerate(text[start:], start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(text[start:i+1])
                        if isinstance(candidate.get("tasks"), list):
                            return candidate
                    except json.JSONDecodeError:
                        pass
                    break

    return None


def validate_plan(plan: dict) -> dict:
    """Validate plan.json structure.

    Args:
        plan: Parsed plan dict

    Returns:
        {"valid": bool, "errors": [...]}
    """
    errors = []

    # Required top-level fields
    if "objective" not in plan:
        errors.append("Missing required field: objective")

    if "tasks" not in plan:
        errors.append("Missing required field: tasks")
    elif not isinstance(plan["tasks"], list):
        errors.append("tasks must be a list")
    elif not plan["tasks"]:
        errors.append("tasks list is empty")
    else:
        # Validate each task
        for i, task in enumerate(plan["tasks"]):
            task_errors = validate_task(task, i)
            errors.extend(task_errors)

    return {"valid": len(errors) == 0, "errors": errors}


def validate_task(task: dict, index: int) -> list:
    """Validate a single task entry.

    Args:
        task: Task dict
        index: Task index for error messages

    Returns:
        List of error strings
    """
    errors = []
    required = ["seq", "slug", "delta", "verify"]

    for field in required:
        if field not in task:
            errors.append(f"Task {index}: missing required field: {field}")

    if "delta" in task:
        if not isinstance(task["delta"], list):
            errors.append(f"Task {index}: delta must be a list")
        elif not task["delta"]:
            # VERIFY tasks legitimately have empty deltas (they only run verification)
            task_type = task.get("type", "BUILD")
            if task_type != "VERIFY":
                errors.append(f"Task {index}: delta list cannot be empty")

    if "seq" in task and not re.match(r"^\d{3}$", str(task["seq"])):
        errors.append(f"Task {index}: seq must be 3-digit string")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Parse planner output for decisions")
    parser.add_argument("input_file", help="Path to planner output file")
    parser.add_argument("--validate", action="store_true",
                        help="Also validate plan.json structure")

    args = parser.parse_args()

    # Read input
    input_path = Path(args.input_file)
    if not input_path.exists():
        print(json.dumps({"error": f"File not found: {input_path}"}))
        sys.exit(1)

    text = input_path.read_text()

    # Detect decision
    result = detect_decision(text)

    # Optionally validate plan
    if args.validate and result.get("plan_json"):
        validation = validate_plan(result["plan_json"])
        result["validation"] = validation

    print(json.dumps(result, indent=2))

    # Exit codes
    if result["decision"] == "CLARIFY":
        sys.exit(2)  # Needs clarification
    elif result["decision"] == "PROCEED":
        sys.exit(0)  # Ready to proceed
    elif result["decision"] == "CONFIRM":
        sys.exit(3)  # Needs confirmation
    else:
        sys.exit(1)  # Unknown/error


if __name__ == "__main__":
    main()
