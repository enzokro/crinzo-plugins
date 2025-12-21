---
description: Check for scope creep against the active Anchor. Run during Build when complexity grows or before Close.
allowed-tools: Read, Bash, Glob
---

# Creep Check

Pause. Compare work-in-progress against the Anchor. Surface what's crept in.

## When to Run

This is a **Build phase** checkpoint. Run it:

- When you sense complexity growing
- Before running `/tether:close`
- When implementation touches more files than expected
- When you catch yourself saying "while we're at it"

## Protocol

1. Find the active workspace file:
   ```bash
   ls workspace/*_active* 2>/dev/null
   ```

2. Read **Anchor**—the fixed point:
   - Scope: What was requested
   - Excluded: What was explicitly out
   - Delta: The planned minimal change

3. Read **Trace**—the reasoning record:
   - Is it being used? (Empty Trace = silent creep)
   - Does each entry connect to Anchor?

4. Compare against recent work:
   - What files changed?
   - What was added beyond the Anchor delta?

5. For each addition, ask:
   - Is this in the Anchor?
   - Does a test require it?
   - Is it present elsewhere in the codebase?

   Three "no"s = creep. Name it. Remove it.

## Report

```
CREEP CHECK

Anchor: [scope from workspace]
Trace: [active | empty | disconnected]

Status: [clean | creeping | crept]

Found:
- [observation]

Crept in:
- [list or "none"]

Action: [continue | remove X | trace reasoning | clarify with user]
```

## Creep Signals

Watch for these in your own reasoning:

| Signal                    | What it reveals           |
| ------------------------- | ------------------------- |
| "flexible," "extensible"  | Over-engineering          |
| "while we're at it"       | Scope expansion           |
| "in case," "future-proof" | Anticipating requirements |
| "also," "and"             | Additive drift            |
| Empty Trace section       | Unexamined implementation |

## Integration

Creep checking is part of the Build phase, not separate from it. The discipline is:

```
Anchor → Build (trace → creep check → implement) → Close
```

If creep is found: name it, remove it, trace why it appeared, continue simpler.
