#!/usr/bin/env python3
"""
Pattern merge with GIGO protection.

Merges synthesis.json from a completed run into the accumulator,
handling missing files, corrupt JSON, and schema validation.

Usage:
    python3 merge_patterns.py --template anki --version v25 \
        --synthesis /path/to/synthesis.json \
        --accumulator /path/to/accumulator.json
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Any


def load_json_safe(path: Path) -> dict | None:
    """Load JSON with GIGO protection."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"Warning: {path} is not a dict, ignoring", file=sys.stderr)
            return None
        return data
    except json.JSONDecodeError as e:
        print(f"Warning: {path} has invalid JSON: {e}", file=sys.stderr)
        return None
    except IOError as e:
        print(f"Warning: Could not read {path}: {e}", file=sys.stderr)
        return None


def validate_pattern(pattern: dict) -> bool:
    """Check pattern has required fields."""
    if not isinstance(pattern, dict):
        return False
    required = ["name"]
    return all(k in pattern for k in required)


def parse_signal(signal_value: Any) -> int:
    """Parse signal from various formats."""
    if isinstance(signal_value, int):
        return signal_value
    if isinstance(signal_value, float):
        return int(signal_value)
    if isinstance(signal_value, str):
        # Parse "+3" or "+3 (high)" format
        cleaned = signal_value.replace("+", "").split()[0].split("(")[0].strip()
        try:
            return int(cleaned)
        except ValueError:
            return 1
    return 1


def merge_pattern(existing: dict, incoming: dict, campaign: str) -> dict:
    """Merge incoming pattern into existing."""
    merged = existing.copy()

    # Increment signal
    existing_signal = parse_signal(existing.get("signal", 0))
    incoming_signal = parse_signal(incoming.get("signal", 1))
    merged["signal"] = existing_signal + incoming_signal

    # Append campaign
    campaigns = set(existing.get("campaigns", []))
    campaigns.add(campaign)
    merged["campaigns"] = sorted(campaigns)

    # Merge other fields (keep existing if conflict, but allow enrichment)
    for key in ["description", "components", "conditions"]:
        if key in incoming:
            if key not in existing:
                merged[key] = incoming[key]
            elif isinstance(incoming[key], str) and len(incoming[key]) > len(str(existing.get(key, ""))):
                # Keep richer description
                merged[key] = incoming[key]

    return merged


def merge_failure_mode(existing: dict, incoming: dict, campaign: str, avoided: bool = False) -> dict:
    """Merge failure mode, tracking occurrences and resolutions."""
    merged = existing.copy()

    if avoided:
        merged["resolutions"] = existing.get("resolutions", 0) + 1
        # Track which campaigns resolved it
        resolved = set(existing.get("resolved", []))
        resolved.add(campaign)
        merged["resolved"] = sorted(resolved)
    else:
        merged["occurrences"] = existing.get("occurrences", 0) + 1

    campaigns = set(existing.get("campaigns", []))
    campaigns.add(campaign)
    merged["campaigns"] = sorted(campaigns)

    # Keep best mitigation (longer is usually more detailed)
    if "mitigation" in incoming:
        existing_mit = existing.get("mitigation", "")
        if len(incoming["mitigation"]) > len(existing_mit):
            merged["mitigation"] = incoming["mitigation"]

    # Merge warn_for lists
    if "warn_for" in incoming:
        warn_for = set(existing.get("warn_for", []))
        warn_for.update(incoming.get("warn_for", []))
        merged["warn_for"] = sorted(warn_for)

    return merged


def extract_patterns_from_synthesis(synthesis: dict) -> list[dict]:
    """Extract patterns from various synthesis formats."""
    patterns = []

    # Direct meta_patterns array
    if "meta_patterns" in synthesis:
        for p in synthesis["meta_patterns"]:
            if validate_pattern(p):
                patterns.append(p)

    # Clusters format (v23-style)
    if "clusters" in synthesis:
        for cluster in synthesis["clusters"]:
            if isinstance(cluster, dict) and "pattern" in cluster:
                patterns.append({
                    "name": cluster.get("name", cluster.get("pattern", "unnamed")),
                    "description": cluster.get("description", cluster.get("pattern", "")),
                    "components": cluster.get("components", []),
                    "signal": cluster.get("signal", 1),
                    "conditions": cluster.get("conditions", "")
                })

    return patterns


def extract_failure_modes(synthesis: dict) -> list[dict]:
    """Extract failure modes from synthesis."""
    failures = []

    # Direct failure_modes array
    if "failure_modes" in synthesis:
        for fm in synthesis["failure_modes"]:
            if isinstance(fm, dict) and "name" in fm:
                failures.append(fm)

    # From conditions (v23-style)
    for key, cond in synthesis.get("conditions", {}).items():
        if "fail" in key.lower() or (isinstance(cond, str) and "fail" in cond.lower()):
            name = key.replace("_", "-")
            failures.append({
                "name": name,
                "description": str(cond) if isinstance(cond, str) else cond.get("failure", str(cond)),
                "occurrences": 1
            })

    return failures


def merge(accumulator: dict, synthesis: dict, campaign: str) -> dict:
    """Main merge logic."""
    result = accumulator.copy()

    # Preserve metadata
    if "domain" not in result and "domain" in synthesis:
        result["domain"] = synthesis["domain"]
    if "framework" not in result and "framework" in synthesis:
        result["framework"] = synthesis["framework"]

    # Initialize if empty
    if "meta_patterns" not in result:
        result["meta_patterns"] = []
    if "failure_modes" not in result:
        result["failure_modes"] = []
    if "evolution" not in result:
        result["evolution"] = []

    # Build lookup by name
    existing_patterns = {p["name"]: p for p in result["meta_patterns"]}
    existing_failures = {f["name"]: f for f in result.get("failure_modes", [])}

    # Extract and merge patterns
    incoming_patterns = extract_patterns_from_synthesis(synthesis)
    for pattern in incoming_patterns:
        name = pattern["name"]
        if name in existing_patterns:
            existing_patterns[name] = merge_pattern(existing_patterns[name], pattern, campaign)
        else:
            pattern["campaigns"] = [campaign]
            if "signal" not in pattern:
                pattern["signal"] = 1
            existing_patterns[name] = pattern

    # Extract and merge failure modes
    incoming_failures = extract_failure_modes(synthesis)
    for fm in incoming_failures:
        name = fm.get("name")
        if not name:
            continue
        if name in existing_failures:
            existing_failures[name] = merge_failure_mode(existing_failures[name], fm, campaign)
        else:
            fm["campaigns"] = [campaign]
            fm["occurrences"] = fm.get("occurrences", 1)
            fm["resolutions"] = fm.get("resolutions", 0)
            existing_failures[name] = fm

    # Merge evolution entries
    if "evolution" in synthesis:
        existing_evolutions = {(e.get("from"), e.get("to")): e for e in result.get("evolution", [])}
        for evo in synthesis["evolution"]:
            key = (evo.get("from"), evo.get("to"))
            if key not in existing_evolutions:
                evo_copy = evo.copy()
                if "campaigns" not in evo_copy:
                    evo_copy["campaigns"] = [campaign]
                result["evolution"].append(evo_copy)

    result["meta_patterns"] = list(existing_patterns.values())
    result["failure_modes"] = list(existing_failures.values())

    return result


def main():
    parser = argparse.ArgumentParser(description="Merge synthesis into accumulator with GIGO protection")
    parser.add_argument("--template", required=True, help="Template name (e.g., anki)")
    parser.add_argument("--version", required=True, help="Version (e.g., v25)")
    parser.add_argument("--synthesis", required=True, help="Path to synthesis.json from run")
    parser.add_argument("--accumulator", required=True, help="Path to accumulator JSON")
    args = parser.parse_args()

    synthesis_path = Path(args.synthesis)
    accumulator_path = Path(args.accumulator)
    campaign = f"{args.template}-{args.version}"

    # Load with GIGO protection
    synthesis = load_json_safe(synthesis_path)
    if synthesis is None:
        print(f"Skipping merge: no valid synthesis at {synthesis_path}")
        return 0

    accumulator = load_json_safe(accumulator_path) or {
        "domain": args.template,
        "framework": "unknown",
        "accumulated_from": [],
        "meta_patterns": [],
        "failure_modes": [],
        "evolution": []
    }

    # Merge
    result = merge(accumulator, synthesis, campaign)

    # Update tracking fields
    accumulated = set(accumulator.get("accumulated_from", []))
    accumulated.add(campaign)
    result["accumulated_from"] = sorted(accumulated)
    result["updated"] = datetime.now().strftime("%Y-%m-%d")

    # Write atomically (tmp + rename prevents corruption)
    accumulator_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = accumulator_path.with_suffix(".tmp")
    try:
        with open(tmp_path, "w") as f:
            json.dump(result, f, indent=2)
        tmp_path.rename(accumulator_path)
    except IOError as e:
        print(f"Error writing accumulator: {e}", file=sys.stderr)
        if tmp_path.exists():
            tmp_path.unlink()
        return 1

    print(f"Merged {campaign} into {accumulator_path}")
    print(f"  Patterns: {len(result['meta_patterns'])}")
    print(f"  Failure modes: {len(result['failure_modes'])}")
    print(f"  Evolution entries: {len(result.get('evolution', []))}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
