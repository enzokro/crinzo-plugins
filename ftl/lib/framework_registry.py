#!/usr/bin/env python3
"""Framework registry for data-driven detection and idiom lookup.

Adding a new framework requires only:
1. Add entry to FRAMEWORK_PATTERNS
2. Update FRAMEWORK_IDIOMS.md with idiom details

No agent prompt changes needed.
"""

import json
import os
import sys
from pathlib import Path

FRAMEWORK_PATTERNS = {
    "fasthtml": {
        "imports": ["from fasthtml"],
        "decorators": ["@rt"],
        "idiom_level": "HIGH",
        "complexity_weight": 3,
        "idiom_ref": "shared/FRAMEWORK_IDIOMS.md#FastHTML"
    },
    "fastapi": {
        "imports": ["from fastapi"],
        "decorators": ["@app.get", "@app.post", "@router.get", "@router.post"],
        "idiom_level": "MODERATE",
        "complexity_weight": 2,
        "idiom_ref": "shared/FRAMEWORK_IDIOMS.md#FastAPI"
    },
    "flask": {
        "imports": ["from flask"],
        "decorators": ["@app.route", "@blueprint.route"],
        "idiom_level": "LOW",
        "complexity_weight": 1,
        "idiom_ref": "shared/FRAMEWORK_IDIOMS.md#Flask"
    },
    "django": {
        "imports": ["from django", "import django"],
        "decorators": ["@login_required", "@require_http_methods"],
        "idiom_level": "MODERATE",
        "complexity_weight": 2,
        "idiom_ref": "shared/FRAMEWORK_IDIOMS.md#Django"
    },
    "litestar": {
        "imports": ["from litestar"],
        "decorators": ["@get", "@post", "@put", "@delete"],
        "idiom_level": "MODERATE",
        "complexity_weight": 2,
        "idiom_ref": "shared/FRAMEWORK_IDIOMS.md#Litestar"
    },
}

# Preference order when coverage equal (more specific first)
FRAMEWORK_PREFERENCE = ["fasthtml", "fastapi", "litestar", "flask", "django"]

FRAMEWORK_IDIOMS = {
    "fasthtml": {
        "required": ["@rt decorator for routes", "Return component trees (Div, P, etc.)"],
        "forbidden": ["Raw HTML strings with f-strings", "Direct Response() with HTML body"]
    },
    "fastapi": {
        "required": ["@app.get/@app.post decorators", "Return Pydantic models for JSON"],
        "forbidden": ["Sync operations in async endpoints", "Raw dict returns without schema"]
    },
    "flask": {
        "required": ["@app.route decorator"],
        "forbidden": []
    },
    "django": {
        "required": ["URL patterns in urls.py", "View functions or class-based views"],
        "forbidden": ["Raw SQL without ORM (unless justified)"]
    },
    "litestar": {
        "required": ["@get/@post decorators", "Return typed responses"],
        "forbidden": ["Sync blocking in async handlers"]
    },
}


def detect(codebase_path: str = ".") -> dict:
    """Detect framework from codebase.

    Returns: {framework, confidence, source, complexity_weight}
    """
    path = Path(codebase_path)

    # Check README for explicit declaration (highest confidence)
    readme_path = path / "README.md"
    if readme_path.exists():
        content = readme_path.read_text()
        if "## Framework Idioms" in content:
            for fw in FRAMEWORK_PATTERNS:
                if fw.lower() in content.lower():
                    return {
                        "framework": fw,
                        "confidence": 0.95,
                        "source": "README.md explicit declaration",
                        "complexity_weight": FRAMEWORK_PATTERNS[fw]["complexity_weight"]
                    }

    # Scan Python files for import patterns
    py_files = list(path.rglob("*.py"))
    if not py_files:
        return {"framework": "none", "confidence": 0.0, "source": "No Python files", "complexity_weight": 0}

    framework_hits = {}
    total_files = len(py_files)

    for py_file in py_files[:100]:  # Limit scan for performance
        try:
            content = py_file.read_text()
            for fw, patterns in FRAMEWORK_PATTERNS.items():
                for imp in patterns["imports"]:
                    if imp in content:
                        framework_hits.setdefault(fw, set()).add(str(py_file))
        except (IOError, UnicodeDecodeError):
            continue

    if not framework_hits:
        return {"framework": "none", "confidence": 0.0, "source": "No framework imports detected", "complexity_weight": 0}

    # Find dominant framework (use FRAMEWORK_PREFERENCE as tiebreaker)
    def sort_key(fw):
        count = len(framework_hits[fw])
        # Lower preference index = higher priority
        pref = FRAMEWORK_PREFERENCE.index(fw) if fw in FRAMEWORK_PREFERENCE else len(FRAMEWORK_PREFERENCE)
        return (count, -pref)  # Higher count wins, then lower preference index

    best_fw = max(framework_hits, key=sort_key)
    hit_count = len(framework_hits[best_fw])

    # Calculate confidence based on coverage
    coverage = hit_count / min(total_files, 100)
    if coverage > 0.5:
        confidence = 0.85
        source = f"Import in >{50}% of files"
    else:
        confidence = 0.75
        source = f"Import detected in {hit_count} file(s)"

    return {
        "framework": best_fw,
        "confidence": confidence,
        "source": source,
        "complexity_weight": FRAMEWORK_PATTERNS[best_fw]["complexity_weight"]
    }


def get_idioms(framework: str) -> dict:
    """Get idiom requirements for framework.

    Returns: {required: [], forbidden: []}
    """
    if framework in FRAMEWORK_IDIOMS:
        return FRAMEWORK_IDIOMS[framework]
    return {"required": [], "forbidden": []}


def get_complexity_weight(framework: str) -> int:
    """Get complexity weight for planner formula."""
    if framework in FRAMEWORK_PATTERNS:
        return FRAMEWORK_PATTERNS[framework]["complexity_weight"]
    return 0


def list_frameworks() -> list:
    """List all registered frameworks."""
    return list(FRAMEWORK_PATTERNS.keys())


def main():
    """CLI interface for framework detection."""
    if len(sys.argv) < 2:
        print("Usage: framework_registry.py <command> [args]", file=sys.stderr)
        print("Commands: detect [path], idioms <framework>, list, weight <framework>", file=sys.stderr)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "detect":
        path = sys.argv[2] if len(sys.argv) > 2 else "."
        result = detect(path)
        print(json.dumps(result, indent=2))
    elif cmd == "idioms":
        if len(sys.argv) < 3:
            print("Usage: framework_registry.py idioms <framework>", file=sys.stderr)
            sys.exit(1)
        result = get_idioms(sys.argv[2])
        print(json.dumps(result, indent=2))
    elif cmd == "weight":
        if len(sys.argv) < 3:
            print("Usage: framework_registry.py weight <framework>", file=sys.stderr)
            sys.exit(1)
        print(get_complexity_weight(sys.argv[2]))
    elif cmd == "list":
        print(json.dumps(list_frameworks()))
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
