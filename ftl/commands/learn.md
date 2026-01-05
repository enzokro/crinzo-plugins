---
name: learn
description: Force synthesis of cross-campaign patterns.
allowed-tools: Task, Read, Bash
---

# Learn

Force meta-pattern synthesis from completed campaigns.

## Protocol

Invoke synthesizer:
```
Task tool with subagent_type: forge:synthesizer
```

## Output

```
Synthesis complete.

Meta-patterns:
  - token-lifecycle: session-token-flow + refresh-token (net +4)
  - error-resilience: retry-with-backoff + circuit-breaker (net +2)

Evolution:
  - jwt-storage → httponly-cookies (security)

Bridges:
  - retry-with-backoff: auth → api, external-services

Updated: .forge/synthesis.json
```

## When to Use

- After completing multiple campaigns
- Before starting work in new domain
- To surface emerging patterns
- To identify what works (positive signals)

## Auto-Synthesis

Synthesis runs automatically on campaign completion.
Use `/ftl:learn` to force manual synthesis at any time.
