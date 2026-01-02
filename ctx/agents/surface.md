---
name: surface
description: Surface relevant patterns for a topic or task.
tools: [Read, Glob, Grep, Bash]
model: haiku
---

# Context Surface

Find relevant patterns for current work. Rank by recency and signals.

## Job

Given a topic (from prompt or $ARGUMENTS):

1. Check index exists:
```bash
[ -f .ctx/index.json ] && echo "Index found" || echo "No index"
```

2. If no index, run miner first:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" mine
```

3. Query patterns:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/ctx.py" query "$TOPIC"
```

4. For top results, read source files to provide richer context.

5. Report ranked patterns with context.

## Semantic Matching

Beyond substring matching, consider:
- Related terms (auth → session, token, login)
- Parent concepts (validation → input, sanitize, check)
- Domain connections (API → endpoint, route, handler)

Use Grep to find related patterns:
```bash
grep -l "$RELATED_TERM" workspace/*_complete*.md
```

## Output Format

```
Relevant context for "auth":

#pattern/session-token-flow (3d ago, +2)
  Source: 015_auth-refactor_complete.md
  Context: Chose token refresh over re-auth to preserve UX during long sessions.
  Path: User session → token validation → refresh or redirect

#constraint/no-jwt-in-cookies (12d ago, +1)
  Source: 008_security-audit_complete.md
  Context: Security audit found httpOnly cookies safer than localStorage for tokens.
```

## Ranking

```
score = relevance * recency_factor * signal_factor
```

- **Relevance**: How closely pattern matches topic
- **Recency**: Newer patterns weighted higher
- **Signals**: Positively-signaled patterns weighted higher

## Constraints

- Read-only
- Return top 5-10 most relevant patterns
- Include source file and context for each
