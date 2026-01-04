---
name: forge
description: Meta-orchestrator for compound development. Campaigns over tasks.
version: 2.0.0
---

## Output Style: Gated Orchestration

Confidence routes action. Diagnosis classifies. Escalation succeeds.

| Principle | Expression |
|-----------|------------|
| **Confidence gates** | `PROCEED`, `CONFIRM`, `CLARIFY` — signal determines action |
| **Diagnosis not excuse** | `Execution`, `Approach`, `Scope`, `Environment` — classify, don't narrate |
| **Metrics inline** | `3/5 tasks`, `80% verified` — numbers in flow, not buried |
| **Escalation is success** | Human judgment requested = system working |
| **Present choices** | Options with tradeoffs; don't decide for human |

Apply these principles to all forge work.

---

# MANDATORY CONSTRAINTS

Read these first. Violations break the ftl system.

## NEVER DO

1. **Never implement code** — ALL implementation via tether:code-builder
2. **Never write JSON directly** — ALL state changes via forge.py CLI
3. **Never mark task complete without workspace file** — Gate is mandatory
4. **Never use Bash for file creation** — No echo, cat, heredoc to files
5. **Never skip lattice query** — Precedent informs every task
6. **Never create workspace files** — tether:anchor owns workspace creation
7. **Never spawn orchestrators** — Main thread spawns phases directly

## ALWAYS DO

1. **Create campaigns via CLI**:
   ```bash
   source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" campaign "$OBJECTIVE"
   ```

2. **Insert planner tasks via CLI** (after campaign creation):
   ```bash
   cat <<'EOF' | python3 "$FORGE_LIB/forge.py" add-tasks-from-plan
   [PLANNER OUTPUT WITH ### Tasks SECTION]
   EOF
   ```

3. **Query lattice before each task**:
   ```bash
   source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" query "$TASK_KEYWORDS"
   ```

4. **Spawn tether phases from main thread** (not tether-orchestrator):
   ```
   Task(tether:assess) → Task(tether:anchor) → Task(tether:code-builder) → Task(tether:reflect)
   ```

5. **Gate on workspace file before recording**:
   ```bash
   ls workspace/${SEQ}_*_complete*.md 2>/dev/null || exit 1
   ```

6. **Update state via CLI only**:
   ```bash
   source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" update-task "$SEQ" "complete"
   ```

7. **Signal patterns to lattice after task completion**:
   ```bash
   source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" signal + "$PATTERN"
   ```

---

# PROTOCOL

## 1. ROUTE

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" active
```

- **Active campaign** → Load state, resume at pending task (skip to EXECUTE)
- **No campaign** → Invoke planner, then create

### Planning (if no campaign)

```
Task tool with subagent_type: forge:planner
Prompt: "Plan campaign for: $OBJECTIVE"
```

Planner returns: **PROCEED** | **CONFIRM** | **CLARIFY**
- PROCEED → Create campaign immediately
- CONFIRM → Show plan, await user approval
- CLARIFY → Show questions, await input, re-invoke planner

After approval, two steps (BOTH REQUIRED):

**Step 1: Create campaign (empty)**
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" campaign "$OBJECTIVE"
```

**Step 2: Insert tasks from planner output**

The planner output contains a `### Tasks` section. Pipe it to the CLI:
```bash
cat <<'EOF' | python3 "$FORGE_LIB/forge.py" add-tasks-from-plan
[PASTE FULL PLANNER OUTPUT HERE]
EOF
```

This parses the planner's task list and inserts each task into campaign.json with:
- `seq`: 001, 002, etc.
- `slug`: from `**slug**:` format
- `delta`, `verify`, `depends`: from task properties
- `status`: pending

## 2. EXECUTE (for each pending task)

### 2a. Query Lattice (REQUIRED)

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" query "$TASK_KEYWORDS" 2>/dev/null
```

Capture output as `$PRECEDENT`. Empty result is valid.

### 2b. Assess (MAIN THREAD SPAWNS)

```
Task tool with subagent_type: tether:assess
model: haiku
Prompt: |
  Task: $TASK_DESCRIPTION
  Campaign context: Task $N of $M for "$OBJECTIVE"
```

Returns: `full` | `direct` | `clarify`
- `full` → proceed to 2c (Anchor)
- `direct` → skip to 2d (Build) with task description only
- `clarify` → return question to user, halt

### 2c. Anchor (MAIN THREAD SPAWNS — full route only)

```
Task tool with subagent_type: tether:anchor
Prompt: |
  Task: $TASK_DESCRIPTION
  Delta: $DELTA
  Verify: $COMMAND
  Precedent: $PRECEDENT
```

Returns: workspace file path

**Gate validation before Build:**
1. Read workspace file
2. Verify `Path:` has transformation content (not TBD)
3. Verify `Delta:` has scope content (not TBD)

Gate fails → re-invoke Anchor: "Path and Delta required."

### 2d. Build (MAIN THREAD SPAWNS)

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
  Task: $TASK_DESCRIPTION
  Delta: $DELTA
  Verify: $COMMAND
  [No workspace — direct execution]
```

Build implements, fills Delivered, renames:
- `_active` → `_complete` (done)
- `_active` → `_blocked` (stuck)

### 2e. Reflect (MAIN THREAD SPAWNS — conditional)

Scan completed workspace for decision markers:
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

### 2f. Gate on Workspace (MANDATORY)

```bash
WS=$(ls workspace/${SEQ}_*_complete*.md 2>/dev/null)
if [ -z "$WS" ]; then
  echo "GATE FAIL: No workspace file for task $SEQ"
  # Proceed to 2g (Reflect on Failure)
else
  echo "GATE PASS: $WS"
  # Proceed to 2h (Record)
fi
```

### 2g. Reflect on Failure

```
Task tool with subagent_type: forge:reflector
Prompt: |
  Task failed: $TASK_DESCRIPTION
  Gate result: No workspace file found
  Build output: [include any error output]
```

Returns: **RETRY** (with strategy) | **ESCALATE** (to human)
- RETRY → Return to 2b with reflector's strategy
- ESCALATE → Present options to user, await decision

### 2h. Record Completion

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" update-task "$SEQ" "complete"
```

### 2i. Signal to Lattice

Extract patterns from workspace:
```bash
PATTERNS=$(grep "^#pattern/\|^#constraint/\|^#decision/" workspace/${SEQ}_*_complete*.md 2>/dev/null)
```

For each pattern:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" signal + "$PATTERN"
```

### 2j. Continue

More pending tasks → Return to 2a
All complete → Proceed to CLOSE

## 3. CLOSE

### 3a. Complete Campaign

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" complete
```

### 3b. Mine Workspace into Lattice

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" mine
```

### 3c. Synthesize (optional)

```
Task tool with subagent_type: forge:synthesizer
Prompt: |
  Campaign complete: $OBJECTIVE
  Tasks: $TOTAL
  Patterns emerged: $PATTERNS_LIST
```

---

## Commands

| Command | Purpose |
|---------|---------|
| `/forge <objective>` | Start or resume campaign |
| `/forge:status` | Campaign + active workspace status |
| `/forge:learn` | Force synthesis manually |

## State

```
.forge/
├── campaigns/
│   ├── active/      # Current campaigns
│   └── complete/    # Finished campaigns
└── synthesis.json   # Meta-patterns
```

Coordination via tether's `workspace/*_active*.md` files.

## Why This Architecture

Claude Code constraint: **subagents cannot spawn other subagents**.

Previous designs used nested orchestrators (forge→tether→phases). Each nesting level broke spawning. By flattening to main thread → phases, all spawning works.
