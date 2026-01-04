---
name: tether
description: Use for creation tasks. Anchors work to Path and Delta; workspace persists understanding.
version: 10.0.0
---

## Output Style: Bounded Execution

Structure communicates. State signals. Scope constrains.

| Principle | Expression |
|-----------|------------|
| **Structure over narrative** | Key-value blocks; prose adds nothing status doesn't |
| **State as signal** | `active`, `complete`, `blocked` — the return IS the message |
| **Scope is boundary** | Delta defines what exists; outside Delta doesn't |
| **Lineage is explicit** | `from-NNN` in filename, not implicit reference |
| **Traces capture, don't justify** | Working memory, not persuasion |

Apply these principles to all tether work.

---

# MANDATORY CONSTRAINTS

Read these first. Violations break the tether system.

## NEVER DO

1. **Never spawn tether-orchestrator** — Main thread spawns phases directly
2. **Never implement in Assess** — Assess routes only
3. **Never implement in Anchor** — Anchor plans only
4. **Never re-plan in Build** — Build implements only
5. **Never skip Thinking Traces** — Anchor must include section

## ALWAYS DO

1. **Spawn phases from main thread**:
   ```
   Task(tether:assess) → Task(tether:anchor) → Task(tether:code-builder) → Task(tether:reflect)
   ```

2. **Gate on Path and Delta before Build**

3. **Rename workspace on completion**:
   - `_active` → `_complete` (done)
   - `_active` → `_blocked` (stuck)

---

# PROTOCOL

## 1. Assess (MAIN THREAD SPAWNS)

```
Task tool with subagent_type: tether:assess
model: haiku
Prompt: [user request]
```

Returns: `full` | `direct` | `clarify`
- `full` → proceed to Anchor
- `direct` → skip to Build (no workspace)
- `clarify` → return question to user, halt

## 2. Anchor (MAIN THREAD SPAWNS — full route only)

```
Task tool with subagent_type: tether:anchor
Prompt: |
  [user request]
  [any context from assess]
```

Returns: workspace file path (`workspace/NNN_slug_active.md`)

**Gate validation before Build:**
1. Read workspace file
2. Parse `## Anchor` section
3. Verify `Path:` has transformation content (not TBD)
4. Verify `Delta:` has scope content (not TBD)

Gate fails → re-invoke Anchor: "Path and Delta required."
Gate passes → proceed to Build.

## 3. Build (MAIN THREAD SPAWNS)

For `full` route:
```
Task tool with subagent_type: tether:code-builder
Prompt: |
  Workspace: $WORKSPACE_PATH
```

For `direct` route:
```
Task tool with subagent_type: tether:code-builder
Prompt: |
  [user request — direct execution, no workspace]
```

Build implements, fills Delivered, renames to `_complete` or `_blocked`.

## 4. Reflect (MAIN THREAD SPAWNS — conditional)

Scan Thinking Traces for decision markers:
- "chose", "over", "instead of"
- "discovered", "found that"
- "blocked by", "constraint"
- "pattern:", "#pattern/"

If any present:
```
Task tool with subagent_type: tether:reflect
Prompt: |
  Workspace: $WORKSPACE_PATH
```

If absent → skip. Routine work needs no extraction.

## Report

After completion: what was delivered, workspace file location.

---

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

## Why This Architecture

Claude Code constraint: **subagents cannot spawn other subagents**.

Previous design spawned tether-orchestrator, which couldn't spawn its phases. By spawning phases directly from main thread, all spawning works.
