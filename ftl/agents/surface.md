---
name: ftl-surface
description: Surface relevant decisions for a topic or task.
tools: [Read, Glob, Grep, Bash]
model: haiku
---

# Context Surface

Find relevant decisions for current work. Rank by recency and signals.

## Job

Given a topic (from prompt or $ARGUMENTS):

1. Check index exists:
```bash
[ -f .ftl/index.json ] && echo "Index found" || echo "No index"
```

2. If no index, run miner first:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/context_graph.py" mine
```

3. Query decisions:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/context_graph.py" query "$TOPIC"
```

4. For top results, read source workspace files to provide richer context.

5. Report ranked decisions with full context.

## Semantic Matching

Beyond substring matching, consider:
- Related terms (auth → session, token, login)
- Parent concepts (validation → input, sanitize, check)
- Domain connections (API → endpoint, route, handler)

Use Grep to find related decisions:
```bash
grep -l "$RELATED_TERM" workspace/*_complete*.md
```

## Output Format

```
Relevant decisions for "auth":

[015] auth-refactor (3d ago, complete)
  Path: User credentials → validation → session token
  Delta: src/auth/*.ts
  Tags: #pattern/session-token-flow (+2)
  Builds on: 008

  Thinking Traces (excerpt):
  Chose token refresh over re-auth to preserve UX during long sessions.

[008] security-audit (12d ago, complete)
  Path: Codebase → security review → findings
  Delta: src/**/*.ts
  Tags: #constraint/no-jwt-in-cookies

  Thinking Traces (excerpt):
  Security audit found httpOnly cookies safer than localStorage for tokens.
```

## Ranking

```
score = relevance * recency_factor * signal_factor
```

- **Relevance**: How closely decision matches topic
- **Recency**: Newer decisions weighted higher
- **Signals**: Positively-signaled patterns weighted higher

## Constraints

- Read-only
- Return top 5-10 most relevant decisions
- Include Path, Delta, Tags, and Traces excerpt for each
