---
name: scout
description: Get proactive suggestions for what to work on.
allowed-tools: Task, Bash, Read
---

# Scout

Surface opportunities and suggest work.

## Protocol

Invoke scout agent:
```
Task tool with subagent_type: forge:scout
```

## Output

Scout returns prioritized suggestions:

```
## Scout Report

### Immediate
- Pending campaign tasks

### Opportunities
- Pattern transfer possibilities
- Synthesis recommendations

### Warnings
- Negative signal patterns
- Stale decisions

### Suggested Next Action
[Most impactful action to take now]
```

## When to Use

- Session start: "What should I work on?"
- Between tasks: "What's next?"
- Before new work: "Any pending campaigns?"
- Periodic check: "What needs attention?"

## Example

```
/ftl:scout

Scout Report:

### Immediate
1. Campaign "auth-refactor" has 3 pending tasks → /forge to resume

### Opportunities
2. Pattern #pattern/retry-backoff (net +4) untested in API domain

### Warnings
3. #pattern/jwt-storage has net -2 signals

### Suggested Next Action
Resume auth-refactor campaign
```
