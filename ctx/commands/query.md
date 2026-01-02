---
description: Surface relevant decisions for a topic.
allowed-tools: Bash, Read, Glob, Grep
---

# Query Decisions

Surface relevant decisions from workspace decision traces.

## Protocol

1. Check for index:
```bash
[ -f .ctx/index.json ] || echo "Run /ctx:mine first"
```

2. Parse $ARGUMENTS for topic.

3. Query decisions:
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
Decisions for 'auth':

[015] auth-refactor (3d ago, complete)
  Path: User credentials → validation → session token
  Delta: src/auth/*.ts
  Tags: #pattern/session-token-flow (+2)
  Builds on: 008

[008] security-audit (12d ago, complete)
  Path: Codebase → security review → findings
  Delta: src/**/*.ts
  Tags: #constraint/no-jwt-in-cookies
```

## Ranking

Decisions ranked by:
- Recency (newer = higher)
- Pattern signals (more + = higher)
- Relevance to topic

## Constraints

- Read-only on workspace
- Returns full decision context, not just patterns
