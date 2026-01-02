---
description: Extract and index patterns from workspace files.
allowed-tools: Bash, Read, Glob, Grep, Write
---

# Mine Patterns

Extract patterns from workspace decision traces. Builds searchable index.

## Protocol

1. Check workspace exists:
```bash
ls workspace/*.md 2>/dev/null || echo "No workspace"
```

2. Extract patterns:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" mine
```

3. Report indexed patterns.

## What Gets Indexed

| Tag Type | Meaning |
|----------|---------|
| `#pattern/` | Reusable structural approach |
| `#constraint/` | Hard rule discovered |
| `#decision/` | Choice made with rationale |
| `#antipattern/` | What failed |
| `#connection/` | Cross-domain insight |

## Output Format

```
Indexed 12 patterns from workspace:
  #pattern/session-token-flow
  #constraint/no-jwt-in-cookies
  #decision/use-httponly
  ...
```

## Index Storage

Patterns stored in `.ctx/index.json`:
```json
{
  "#pattern/session-token-flow": {
    "source": "015_auth-refactor_complete.md",
    "mtime": 1704067200,
    "depth": 2,
    "context": "Chose token refresh over re-auth for UX"
  }
}
```

## When to Mine

- After completing workspace tasks
- Before querying if index is stale
- Periodically to capture new patterns

## Constraints

- Only reads workspace files
- Only writes to .ctx/index.json
