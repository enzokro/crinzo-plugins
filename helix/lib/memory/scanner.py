"""Content security scanner for stored insights.

Prevents indirect prompt injection via derived insights.
Attack vector: malicious code comment → agent quotes in BLOCKED reason
→ extract_insight() derives insight → stored → injected into future prompts.

Pure functions, stdlib only.
"""

import re
from typing import Optional, Tuple

# --- Pattern categories ---

# Prompt injection: multi-word sequences to avoid false positives on normal language
_INJECTION_PATTERNS = [
    re.compile(
        r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|rules|prompts)",
        re.IGNORECASE,
    ),
    re.compile(
        r"you\s+are\s+now\s+(?:a\s+)?(?:new|different|my)",
        re.IGNORECASE,
    ),
    re.compile(
        r"<\s*(?:system|instruction|prompt)\s*>",
    ),
    re.compile(
        r"(?:forget|disregard|override)\s+(?:your|all|the)\s+(?:instructions|rules|context)",
        re.IGNORECASE,
    ),
    re.compile(
        r"do\s+not\s+tell\s+the\s+user",
        re.IGNORECASE,
    ),
]

# Credential leak: broad key=value pattern (relaxed for prescriptive content)
_CREDENTIAL_GENERIC = [
    re.compile(
        r"(?:api[_-]?key|secret[_-]?key|password|token|bearer)\s*[:=]\s*[\"']?\S{8,}",
        re.IGNORECASE,
    ),
]

# Credential leak: provider-specific formats (NEVER relaxed)
_CREDENTIAL_SPECIFIC = [
    re.compile(r"(?:AKIA|AGPA|ASIA)[A-Z0-9]{16}"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),
    re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
]

# Invisible unicode: zero-width chars used to hide content
_UNICODE_PATTERNS = [
    re.compile(r"[\u200b\u200c\u200d\u2060\ufeff\u00ad]"),
]

# Exfiltration: attempts to load external resources
_EXFIL_PATTERNS = [
    re.compile(
        r"""(?:fetch|curl|wget|requests\.get)\s*\(\s*["']https?://""",
    ),
    re.compile(
        r"""<img\s+src\s*=\s*["']https?://""",
        re.IGNORECASE,
    ),
    re.compile(
        r"!\[.*?\]\(https?://[^)]*\)",
    ),
]

# Prescriptive content: insights that teach rather than contain secrets
_PRESCRIPTIVE_PATTERNS = [
    re.compile(r"^When\s+", re.IGNORECASE),
    re.compile(r"be aware that", re.IGNORECASE),
    re.compile(r"^Consider\s+", re.IGNORECASE),
    re.compile(r"^Always\s+", re.IGNORECASE),
    re.compile(r"^Never\s+", re.IGNORECASE),
]


def _is_prescriptive(content: str) -> bool:
    """Check if content is a prescriptive insight (teaching pattern)."""
    return any(p.search(content) for p in _PRESCRIPTIVE_PATTERNS)


# Combined mapping: category name → pattern list
_CATEGORIES = {
    "prompt_injection": _INJECTION_PATTERNS,
    "credential_generic": _CREDENTIAL_GENERIC,
    "credential_specific": _CREDENTIAL_SPECIFIC,
    "invisible_unicode": _UNICODE_PATTERNS,
    "exfiltration": _EXFIL_PATTERNS,
}

# Categories that are NEVER relaxed for prescriptive content
_STRICT_CATEGORIES = {
    "prompt_injection",
    "credential_specific",
    "invisible_unicode",
    "exfiltration",
}


def scan(content: str) -> Tuple[bool, Optional[str]]:
    """Scan content for security threats.

    Args:
        content: Text to scan.

    Returns:
        (True, None) if clean.
        (False, "category: matched_text") if blocked.
    """
    if not content:
        return True, None

    is_prescriptive = _is_prescriptive(content)

    for category, patterns in _CATEGORIES.items():
        if is_prescriptive and category not in _STRICT_CATEGORIES:
            continue
        for pattern in patterns:
            match = pattern.search(content)
            if match:
                return False, f"{category}: {match.group()}"

    return True, None
