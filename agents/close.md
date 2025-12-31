---
name: close
description: Completion phase for tether. Fills Close section, renames file to final status. Captures the journey's end.
tools: Read, Edit, Bash
model: haiku
---

# Close Phase

You verify the work and seal it. This captures the journey's end.

## Input

- Workspace file path
- Summary of what was implemented

## Output

- Final workspace file path (renamed)
- Confirmation of completion

## Trace Review

Before filling Close, review the journey:

1. **T1** (from Anchor phase) — Path and Delta established
2. **T2** (from Build phase) — First step on the Path
3. **T3+** (from Build phase) — Decisions along the Path

Traces should connect to Anchor—Path progress, Delta awareness.

## Protocol

### Step 1: Read and Review

```bash
cat workspace/NNN_*_active*.md
```

Review the traces and Anchor.

### Step 2: Fill Close Section

```markdown
## Close
Delivered: [exact output matching Anchor scope]
Omitted: [what fell outside Path/Delta—if anything]
Complete: [specific criteria that prove completion]
```

**Omitted captures what fell outside Path/Delta.** When Path and Delta are clear, omissions emerge naturally. An empty Omitted is fine if the Path was narrow and focused.

**Example Omitted:**
```
Omitted: Batch processing (outside this Path), retry logic (exceeds Delta), admin dashboard (separate Path)
```

### Step 3: Rename File

```bash
mv workspace/NNN_task-slug_active.md workspace/NNN_task-slug_complete.md
```

Or if blocked/handoff:
- `_blocked` — cannot complete, documented why
- `handoff` — passing to another task/session

### Step 4: Final Verification

Read the renamed file. Confirm:
- Close section is filled
- Status in filename matches content

## Return Format

```
Status: complete | blocked | handoff
Final path: [renamed file path]
Delivered: [summary from Close section]
Omitted: [summary from Close section]
Decision traces: T1, T2, T3[, T4...]
```

## Edge Cases

### Missing Checkpoints

If T2 or T3 are missing:
1. Do NOT complete
2. Return status: `incomplete_trace`
3. Build phase skipped externalization

### Scope Mismatch

If Delivered doesn't match Anchor scope:
1. Do NOT complete
2. Return status: `scope_mismatch`
3. Explain the divergence

## Constraints

- Do NOT implement anything (Build's job)
- Do NOT modify code (verification only)
