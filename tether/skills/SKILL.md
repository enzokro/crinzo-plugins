---
name: tether
description: Use for creation tasks. Anchors work to Path and Delta; workspace persists understanding.
version: 9.2.0
---

# Tether

Deliver exactly what was requested. Path and Delta are your anchors.

## First Action

Invoke orchestrator:
```
Task tool with subagent_type: tether:tether-orchestrator
```

Pass the user's request. Do NOT route or implement directly.

## Flow

```
tether:assess (haiku) → route
tether:anchor → Path + Delta + Thinking Traces
tether:build → implement, complete
tether:reflect → extract patterns (conditional)
```

Routes: `full` (workspace file) | `direct` (execute) | `clarify` (ask user)

Gate: Path and Delta must exist before Build.

## Constraints

| Constraint | Meaning |
|------------|---------|
| Present over future | Current request only |
| Concrete over abstract | Specific solution, not framework |
| Explicit over clever | Clarity over sophistication |
| Edit over create | Modify existing first |

No new abstractions. No files outside Delta.

## Workspace

```
workspace/NNN_task-slug_status[_from-NNN].md
```

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change]

## Thinking Traces
[findings, decisions]

## Delivered
[filled at completion]
```

Query patterns:
```bash
grep -h "^#pattern/\|^#constraint/\|^#decision/" workspace/*_complete*.md | sort -u
```

## Phase Boundaries

```
Assess: route only     → Anchor: plan only     → Build: implement only
No exploring             No implementing          No re-planning
No creating files        No skipping Traces       No new abstractions
```

## Creep Signals

| Signal | Meaning |
|--------|---------|
| "flexible," "extensible" | Exceeds Delta |
| "while we're at it" | Off Path |
| "in case," "future-proof" | Exceeds Delta |

Invoke `/tether:creep` when drift detected.
