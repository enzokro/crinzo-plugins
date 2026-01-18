---
version: 1.0
---

# Error Matching Rules

This document defines the error matching algorithm used by Builder for retry decisions and Observer for failure extraction.

See [ONTOLOGY.md](ONTOLOGY.md#block-status) for BLOCK vs FAIL distinction and discovery semantics.

## Matching Algorithm

```
FOR each failure in prior_knowledge/failure:
  # 1. Semantic match (preferred - more robust)
  IF semantic_similarity(error_msg, failure.trigger) > 0.6:
    RETURN failure

  # 2. Regex match (fallback - for exact patterns)
  IF failure.match AND regex_match(failure.match, error_trace):
    RETURN failure

RETURN None  # No match - discovery needed
```

## Match Types

| Type | Rule | Use Case |
|------|------|----------|
| **Semantic** | similarity > 0.6 | General error messages |
| **Regex** | `failure.match` pattern | Stack traces, specific formats |

## Semantic Similarity Examples

| Error A | Error B | Similarity | Match? |
|---------|---------|------------|--------|
| "ModuleNotFoundError: {module}" | "ImportError: cannot import {module}" | ~0.75 | YES |
| "pytest: no tests ran" | "test collection failed" | ~0.65 | YES |
| "Framework idiom violation: {pattern}" | "Idiom check failed: {pattern}" | ~0.70 | YES |
| "SyntaxError: unexpected EOF" | "IndentationError" | ~0.45 | NO |
| "Connection refused" | "Database error" | ~0.30 | NO |

## Regex Pattern Examples

| Pattern | Matches |
|---------|---------|
| `.*ModuleNotFound.*` | Any ModuleNotFoundError |
| `AssertionError:.*expected.*got` | Assertion failures with expected/got |
| `TypeError:.*argument.*` | Type mismatches in function calls |

## Priority Order

1. **Semantic match first** - More robust to wording variations
2. **Regex fallback** - For structured error formats

## Actions After Match

| Match Result | Builder Action | Observer Action |
|--------------|----------------|-----------------|
| Match found, budget >= 2 | Apply fix, retry | Link to existing failure |
| Match found, budget < 2 | BLOCK (budget exhausted) | Note budget issue |
| No match | BLOCK (discovery needed) | Extract new failure |

## Discovery vs. Retry

- **Retry**: Error matches known failure with known fix
- **Discovery**: Error is new, needs Observer to extract pattern

Builder MUST NOT attempt fixes for unmatched errors. This preserves learning opportunities.
