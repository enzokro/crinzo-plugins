---
description: Surface relevant patterns for a topic.
allowed-tools: Bash, Read, Glob, Grep
---

# Query Context

Surface relevant patterns from workspace decision traces.

## Protocol

1. Check for index:
```bash
[ -f .ctx/index.json ] || echo "Run /ctx:mine first"
```

2. Parse $ARGUMENTS for topic.

3. Query patterns:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" query "$TOPIC"
```

4. If no index exists, invoke miner first:
```
Task tool with subagent_type: ctx:miner
```
Then re-query.

## Output Format

```
Patterns matching 'auth':
  #pattern/session-token-flow (3d, +2) from 015_auth-refactor_complete.md
    Chose token refresh over re-auth for UX...
  #constraint/no-jwt-in-cookies (12d, +1) from 008_security-audit_complete.md
    Security audit found cookie exposure risk...
```

## Weighting

Patterns ranked by:
- Recency (newer = higher)
- Signals (more + = higher)
- Relevance to topic

## Constraints

- Read-only on workspace
- No modification to patterns
