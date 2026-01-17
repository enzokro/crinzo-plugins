# Framework Idioms Reference

This document defines framework detection rules and idiom requirements shared across FTL agents.

## Framework Detection

| Import Pattern | Framework | Idiom Level |
|----------------|-----------|-------------|
| `from fasthtml` | FastHTML | HIGH (strict enforcement) |
| `from fastapi` | FastAPI | MODERATE |
| `from flask` | Flask | LOW |
| None detected | none | NONE |

## Idiom Requirements by Framework

### FastHTML (HIGH)

| Type | Rule | Rationale |
|------|------|-----------|
| **Required** | `@rt` decorator for routes | Framework convention |
| **Required** | Return component trees (Div, P, etc.) | Type-safe rendering |
| **Forbidden** | Raw HTML strings with f-strings | XSS risk, bypasses component model |
| **Forbidden** | Direct `Response()` with HTML body | Loses component benefits |

### FastAPI (MODERATE)

| Type | Rule | Rationale |
|------|------|-----------|
| **Required** | `@app.get/@app.post` decorators | Framework convention |
| **Required** | Return Pydantic models for JSON | Type validation |
| **Forbidden** | Sync operations in async endpoints | Blocks event loop |
| **Forbidden** | Raw dict returns without schema | Loses validation |

### Flask (LOW)

| Type | Rule | Rationale |
|------|------|-----------|
| **Required** | `@app.route` decorator | Framework convention |
| **Forbidden** | None enforced | Flexible framework |

### None

No idiom requirements or restrictions.

## Detection Priority

1. Check `README.md` for explicit "Framework Idioms" section (highest confidence)
2. Grep for import statements (medium confidence)
3. Check `pyproject.toml` or `requirements.txt` for dependencies (fallback)

## Idiom Compliance Checking

Agents MUST verify idiom compliance at these points:

| Agent | Check Point | Action on Violation |
|-------|-------------|---------------------|
| Explorer | Pattern detection | Report in exploration.json |
| Planner | Task design | Include idioms in plan.json |
| Builder | PLAN + QUALITY states | BLOCK (idiom violation) |
| Observer | Pattern extraction | Note systemic idiom issues |
