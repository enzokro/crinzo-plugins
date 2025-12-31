---
description: Check for scope creep against Path and Delta. Run during Build when complexity grows.
allowed-tools: Read, Bash, Glob
---

# Creep Check

Pause. Compare work-in-progress against Path and Delta.

## When to Run

Run it when:
- You sense complexity growing
- Implementation touches more files than expected
- You catch yourself saying "while we're at it"

## Protocol

1. Find the active workspace file:
   ```bash
   ls workspace/*_active* 2>/dev/null
   ```

2. Read **Anchor**—the fixed point:
   - Path: The data transformation
   - Delta: The minimal change

3. Compare against recent work:
   - Am I still on the Path?
   - Am I within Delta?

4. For each addition beyond Path/Delta, ask:
   - Is this on the Path?
   - Does it exceed Delta?

   If yes = creep. Name it. Remove it.

## Report

```
CREEP CHECK

Path: [from workspace]
Delta: [from workspace]

Status: [clean | creeping]

Off Path:
- [list or "none"]

Exceeds Delta:
- [list or "none"]

Action: [continue | remove X | clarify with user]
```

## Creep Signals

Watch for these in your own reasoning:

| Signal                    | What it reveals       |
| ------------------------- | --------------------- |
| "flexible," "extensible"  | Exceeding Delta       |
| "while we're at it"       | Off Path              |
| "in case," "future-proof" | Exceeding Delta       |
| "also," "and"             | Off Path              |

If creep is found: name it, remove it, continue simpler.
