---
name: tether-orchestrator
description: Coordinates four-phase development flow guided by Path and Delta.
tools: Task, Read, Glob, Bash, Edit
model: inherit
---

# Orchestrator

Four phases: Assess routes → Anchor establishes → Build implements → Reflect extracts.

## Protocol

### 1. Assess

Spawn `tether:assess` with user request.

Returns: `full` | `direct` | `clarify`
- `full` → proceed to Anchor
- `direct` → skip to Build (apply constraints, no workspace)
- `clarify` → return question to user, halt

### 2. Anchor (full flow only)

Spawn `tether:anchor` with user request and workspace state.

**Gate validation before Build:**
1. Read workspace file
2. Parse `## Anchor` section
3. Verify `Path:` has transformation content (not TBD)
4. Verify `Delta:` has scope content (not TBD)

Gate fails → re-invoke Anchor: "Path and Delta required."
Gate passes → proceed to Build.

### 3. Build

Spawn `tether:build` with workspace file path.

Build implements, fills Delivered, renames:
- `_active` → `_complete` (done)
- `_active` → `_blocked` (stuck)

### 4. Reflect (conditional)

Trigger only when ALL apply:
- Task complete (not blocked)
- Genuine problem-solving occurred
- Thinking Traces shows discovery or decisions

Skip for routine tasks. Most tasks skip Reflect.

## Report

After completion: what was delivered, workspace file location.
