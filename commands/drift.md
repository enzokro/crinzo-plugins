---
description: Review recent work against the workspace anchor for drift. User-initiated semantic awareness.
allowed-tools: Read, Bash, Glob
---

# Drift Review

Review recent work against the active workspace anchor.

## Philosophy

This is awareness, not enforcement. The questions help you think.

"Internalized discipline replaces external enforcement."

## Protocol

1. Find active workspace file:
   ```bash
   ls workspace/*_active* 2>/dev/null
   ```

   If none found, report: "No active workspace. Nothing to review against."

2. Read the Anchor section - this is the scope boundary:
   - **Scope**: The exact requirement
   - **Excluded**: What was explicitly out of scope

3. Examine recent work:
   - What files were changed?
   - What was added beyond the Anchor delta?

4. For each addition, ask the detection questions:
   - Was this explicitly requested in the Anchor?
   - Does a test require it?
   - Is it present elsewhere in the codebase?

5. Report:

```
DRIFT REVIEW

Anchor: [one-sentence behavior from workspace file]

Alignment: [matches | partial | drifted]

Findings:
- [observation 1]
- [observation 2]

Additions beyond scope:
- [list or "none detected"]

Recommendation: [continue | remove X | clarify scope with user]
```

## Detection Patterns

These are thought patterns to notice, not syntax to grep:

| Pattern | Question to Ask |
|---------|-----------------|
| Over-engineering | "Did I create abstractions not in the anchor?" |
| Scope creep | "Did I add 'and also' work?" |
| Verbosity | "Is there explanation beyond what's needed?" |
| Pattern violation | "Did I introduce new architecture?" |
| Future-proofing | "Did I build for requirements that don't exist?" |

## When to Use

- After completing a significant piece of work
- Before running `/tether:close`
- When you sense complexity growing
- When uncertain if you've stayed in scope

This command is a mirror, not a judge.
