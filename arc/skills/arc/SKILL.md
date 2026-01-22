# Arc

A learning layer for Claude Code. Memory that compounds. Metacognition that knows when to pivot.

---

## Command Execution

### /arc:recall <query>

Query memory for relevant failures and patterns.

```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py recall "$QUERY"
```

**Show the user**: Relevant memories ranked by score. For each memory, show:
- Name and type (failure/pattern)
- Trigger (when this applies)
- Resolution/insight (what to do)
- Effectiveness score

If no memories match, say so.

---

### /arc:health

Check learning system status.

```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py health
```

**Show the user**:
- Total memories and breakdown by type
- Overall effectiveness
- Any issues (e.g., embeddings unavailable)

---

### /arc:meta

Check if current approach is working. Requires an active session.

```bash
python3 {{PLUGIN_ROOT}}/lib/meta.py assess --session "$SESSION_ID"
```

**Show the user**:
- Status (healthy/struggling/failing)
- Success rate
- Consecutive failures
- Recommendation (keep_going/slow_down/consider_pivot/pivot_now)

If no session active, say "No session tracked. Start one with task.py new-session."

---

### /arc:chunk

Extract a pattern from successful work. Interactive.

**Ask the user**:
1. What was the task/objective?
2. What approach worked?

Then run:
```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py chunk --task "$TASK" --outcome "SUCCESS" --approach "$APPROACH"
```

**Show the user**: Whether pattern was created or existing one strengthened.

---

### /arc:decay

Show memories that would decay due to lack of use.

```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py decay --days 30 --min-uses 2
```

**Show the user**: List of memories that haven't been used in 30 days with fewer than 2 feedback events. These are candidates for forgetting.

---

### /arc:consolidate

Merge highly similar memories.

```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py consolidate
```

**Show the user**: How many memories were merged.

---

## When to Use Arc (Proactively)

### Before Starting Complex Work

Query memory for relevant context:
```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py recall "the objective"
```

Inject any relevant failures/patterns into your thinking.

### After Completing Work Successfully

Store what worked:
```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py chunk --task "..." --outcome "SUCCESS" --approach "..."
```

### After Failing

Store the failure so it's not repeated:
```bash
python3 {{PLUGIN_ROOT}}/lib/memory.py store --type failure --trigger "what went wrong" --resolution "what to do instead"
```

### When Stuck Multiple Times

Check metacognition:
```bash
python3 {{PLUGIN_ROOT}}/lib/meta.py assess --session "$SESSION_ID"
```

If it says pivot, try a different approach.

---

## Session Management

For tracking success/failure across a conversation:

```bash
# Start a session
python3 {{PLUGIN_ROOT}}/lib/task.py new-session
# Returns: {"session_id": "abc123"}

# Record outcome after each task
python3 {{PLUGIN_ROOT}}/lib/meta.py record --session "abc123" --seq 1 --success --notes "worked"
python3 {{PLUGIN_ROOT}}/lib/meta.py record --session "abc123" --seq 2 --notes "failed because..."

# Check if approach is working
python3 {{PLUGIN_ROOT}}/lib/meta.py assess --session "abc123"
```

---

## Feedback Loop (Critical)

When completing a task that used arc memories:

```bash
python3 {{PLUGIN_ROOT}}/lib/task.py complete \
  --session "$SESSION_ID" \
  --seq $SEQ \
  --delivered "what was delivered" \
  --utilized '["memory-names-that-actually-helped"]'
```

This automatically updates memory effectiveness:
- Memories you used → helped++
- Memories injected but unused → failed++

**Be honest about UTILIZED.** This is how the system learns which memories are valuable.

---

## Guidance References

For deeper cognitive guidance, see:
- `guidance/reason.md` - How to think: impasse detection, complexity assessment
- `guidance/act.md` - How to act: verification, honest reporting

---

## Environment

```
PLUGIN_ROOT={{PLUGIN_ROOT}}
Database: {{PLUGIN_ROOT}}/.arc/arc.db
```
