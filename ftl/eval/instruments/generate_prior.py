#!/usr/bin/env python3
"""
Generate prior knowledge section for planner prompt injection.

Reads the accumulated patterns from memory and generates a markdown
section that can be prepended to the planner prompt.

Usage:
    python3 generate_prior.py /path/to/accumulator.json
    python3 generate_prior.py /path/to/accumulator.json --output /path/to/output.md
"""

import json
import sys
import argparse
from pathlib import Path


def load_accumulator(path: Path) -> dict | None:
    """Load accumulator with error handling."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def generate_prior_knowledge(data: dict) -> str:
    """Generate markdown prior knowledge section."""
    lines = [
        "# Prior Knowledge (from previous campaigns)",
        "",
        "This knowledge comes from successful campaigns. Use it to inform your planning.",
        ""
    ]

    # High-signal patterns (signal >= 2)
    patterns = sorted(
        data.get("meta_patterns", []),
        key=lambda p: p.get("signal", 0),
        reverse=True
    )

    high_signal_patterns = [p for p in patterns if p.get("signal", 0) >= 2]

    if high_signal_patterns:
        lines.append("## Meta-Patterns (high confidence)")
        lines.append("")

        for p in high_signal_patterns[:5]:  # Top 5 only
            signal = p.get("signal", 0)
            name = p.get("name", "unnamed")

            lines.append(f"**{name}** (signal: +{signal})")

            # Pattern description
            if "description" in p:
                lines.append(f"- Pattern: {p['description']}")
            elif "components" in p:
                lines.append(f"- Pattern: {' → '.join(p['components'])}")

            # Conditions
            if "conditions" in p:
                lines.append(f"- Conditions: {p['conditions']}")

            # Use case hint
            if "components" in p:
                lines.append(f"- Use for: {_infer_use_case(p)}")

            lines.append("")

    # Failure modes (always include - these prevent expensive mistakes)
    failures = data.get("failure_modes", [])

    if failures:
        lines.append("## Known Failure Modes")
        lines.append("")

        for fm in failures:
            name = fm.get("name", "unnamed")
            occurrences = fm.get("occurrences", 0)
            resolutions = fm.get("resolutions", 0)

            # Estimate impact (50K tokens per occurrence is rough average)
            impact = occurrences * 50

            lines.append(f"**{name}** (impact: ~{impact}K tokens when hit)")

            if "description" in fm:
                lines.append(f"- Issue: {fm['description']}")

            # Symptom if available
            if "symptom" in fm:
                lines.append(f"- Symptom: {fm['symptom']}")

            if "mitigation" in fm:
                lines.append(f"- Mitigation: {fm['mitigation']}")

            # Warn builders about this
            if "warn_for" in fm:
                warn_list = ", ".join(fm["warn_for"])
                lines.append(f"- **WARN builders** when: Task involves {warn_list}")

            lines.append("")

    # Verification patterns if present
    verification = data.get("verification_patterns", {})
    if verification:
        lines.append("## Verification Patterns")
        lines.append("")
        lines.append("| Task Type | Verify Command |")
        lines.append("|-----------|----------------|")
        for task_type, cmd in verification.items():
            lines.append(f"| {task_type.replace('-', ' ').title()} | `{cmd}` |")
        lines.append("")

    # How to use
    lines.append("## How to Use This")
    lines.append("")
    lines.append("1. **Reference patterns** in task design when they match")
    lines.append("2. **Include warnings** in task Done-when for known failure modes")
    lines.append("3. **Note in rationale**: \"Pattern match: layered-build\"")
    lines.append("")

    return "\n".join(lines)


def _infer_use_case(pattern: dict) -> str:
    """Infer use case from pattern structure."""
    name = pattern.get("name", "").lower()
    components = pattern.get("components", [])

    if "layered" in name or "build" in name:
        return "Sequential task dependencies with foundation-first approach"
    if "dataclass" in name or "sync" in name:
        return "FastHTML apps with SQLite persistence"
    if "redirect" in name or "post" in name:
        return "Any state-changing route (create, update, delete, rate)"
    if "algorithm" in name or "state" in name:
        return "Simple per-entity algorithm state storage"

    # Generic fallback
    if components:
        return f"Tasks involving {', '.join(components[:2])}"

    return "Matching task structures"


def main():
    parser = argparse.ArgumentParser(description="Generate prior knowledge markdown")
    parser.add_argument("accumulator", help="Path to accumulator JSON")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()

    accumulator_path = Path(args.accumulator)

    data = load_accumulator(accumulator_path)
    if data is None:
        # No accumulator = de novo run, output nothing
        if args.output:
            Path(args.output).write_text("")
        return 0

    markdown = generate_prior_knowledge(data)

    if args.output:
        Path(args.output).write_text(markdown)
        print(f"Generated prior knowledge at {args.output}")
    else:
        print(markdown)

    return 0


if __name__ == "__main__":
    sys.exit(main())
