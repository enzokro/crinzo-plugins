---
description: Check for scope creep against Path and Delta.
allowed-tools: Read, Bash, Glob
---

# Creep Check

Run when complexity grows or more files touched than expected.

## Protocol

Find active workspace:
```bash
ls workspace/*_active* 2>/dev/null
```

Read Anchor (Path and Delta = fixed points).

Compare recent work:
- Am I on Path?
- Within Delta?

For each addition beyond scope: creep. Name it. Remove it.

## Report

```
Path: [from workspace]
Delta: [from workspace]

Status: clean | creeping

Off Path: [list or none]
Exceeds Delta: [list or none]

Action: continue | remove X
```

## Signals

| Signal | Meaning |
|--------|---------|
| "flexible," "extensible" | Exceeds Delta |
| "while we're at it" | Off Path |
| "in case," "future-proof" | Exceeds Delta |
