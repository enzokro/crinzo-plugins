---
name: forge
description: Meta-orchestrator for compound development. Campaigns over tasks.
version: 1.0.1
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

# Forge

Campaigns. Precedent. Synthesis. Growth.

## Protocol

Execute directly in main thread. Do NOT spawn forge-orchestrator as subagent — subagents cannot spawn other subagents, which breaks tether delegation.

### 1. ROUTE

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" active
```

- **Active campaign exists** → Load state, resume at pending task
- **No campaign** → Create via CLI:
  ```bash
  source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" campaign "$OBJECTIVE"
  ```

If campaign needs task decomposition, use planner for analysis only:
```
Task tool with subagent_type: forge:planner
Prompt: "Plan tasks for: $OBJECTIVE"
```
Then add tasks via CLI based on planner output.

### 2. EXECUTE (for each pending task)

**2a. Query Lattice**
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" query "$TASK_KEYWORDS"
```

**2b. Delegate to Tether**
```
Task tool with subagent_type: tether:tether-orchestrator
Prompt: |
  Task: $DESCRIPTION
  Delta: $FILES
  Verify: $COMMAND
  Campaign context: Task $N of $M for "$OBJECTIVE"
  Precedent: $LATTICE_RESULTS
```

**2c. Gate on Workspace**
```bash
ls workspace/*_complete*.md 2>/dev/null | grep "$SEQ"
```
- File exists → proceed to 2d
- No file → invoke reflector, retry or escalate

**2d. Record Completion**
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" update-task "$SEQ" "complete"
```

**2e. Signal Patterns**
Extract tags from workspace file, signal each:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" signal + "$PATTERN"
```

### 3. CLOSE (when all tasks complete)

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" complete
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" mine
```

Optionally invoke synthesizer for meta-learning:
```
Task tool with subagent_type: forge:synthesizer
```

---

## Constraints

| Constraint | Meaning |
|------------|---------|
| **Execute in main thread** | Do not spawn forge-orchestrator — it can't spawn tether |
| **Delegate over implement** | Tether does all implementation work |
| **Precedent over discovery** | Query lattice before each task |
| **Gate before record** | Workspace file must exist before marking complete |
| **Mine on close** | Always mine workspace after campaign completion |

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

Previous design spawned forge-orchestrator as subagent, which then couldn't spawn tether-orchestrator. By executing the forge protocol in main thread, tether delegation works correctly.
