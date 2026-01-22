# Arc

A learning layer for Claude Code. Memory that compounds. Metacognition that knows when to pivot.

**Plugin root**: This skill's files are at the path where this SKILL.md lives. All commands use paths relative to that root.

---

## Commands

### /arc:recall \<query\>

Query memory for relevant failures and patterns.

```bash
python3 lib/memory.py recall "<query>"
```

Run from the arc plugin root directory.

**Output**: Show memories ranked by score. For each:
- Name, type (failure/pattern)
- Trigger → Resolution
- Score (relevance × effectiveness × recency)

If empty, say "No relevant memories found."

---

### /arc:store

Store a new failure or pattern. Interactive.

**Ask**:
1. Type: failure or pattern?
2. Trigger: When does this apply?
3. Resolution: What to do?

```bash
python3 lib/memory.py store --type "<failure|pattern>" --trigger "<trigger>" --resolution "<resolution>"
```

**Output**: Confirm what was stored.

---

### /arc:learn

Close the feedback loop after completing work. Interactive.

**Ask**:
1. What memories were injected (shown to you)?
2. Which ones did you actually use?

```bash
python3 lib/memory.py feedback --utilized '["name1", "name2"]' --injected '["name1", "name2", "name3"]'
```

**Output**: Show how many memories were marked as helpful vs unhelpful.

---

### /arc:chunk

Extract a pattern from successful work. Interactive.

**Ask**:
1. What was the task?
2. What approach worked?

```bash
python3 lib/memory.py chunk --task "<task>" --outcome "SUCCESS" --approach "<approach>"
```

**Output**: Confirm pattern created or strengthened.

---

### /arc:health

Check learning system status.

```bash
python3 lib/memory.py health
```

**Output**: Total memories, effectiveness, issues.

---

### /arc:meta

Check if current approach is working.

```bash
python3 lib/meta.py assess --session "<session_id>"
```

If no session, say "No session tracked."

**Output**: Status, success rate, recommendation (keep_going/pivot).

---

### /arc:decay

Show memories that would decay.

```bash
python3 lib/memory.py decay
```

**Output**: Memories unused for 30+ days with minimal feedback.

---

### /arc:consolidate

Merge similar memories.

```bash
python3 lib/memory.py consolidate
```

**Output**: How many merged.

---

## Proactive Usage

### Before Complex Work

Read the guidance, then query memory:

```bash
# Read guidance/reason.md for how to think
# Then:
python3 lib/memory.py recall "<what you're about to do>"
```

Inject relevant memories into your thinking.

### After Success

Store what worked:

```bash
python3 lib/memory.py chunk --task "..." --outcome "SUCCESS" --approach "..."
```

### After Failure

Store so it's not repeated:

```bash
python3 lib/memory.py store --type failure --trigger "..." --resolution "..."
```

### When Stuck Repeatedly

Check metacognition. If failing, pivot.

---

## The Feedback Loop

This is how arc learns:

1. **Query** memory before work → get injected memories
2. **Work** using (or not using) those memories
3. **Report** which memories you actually utilized
4. **Memory updates**: utilized → helped++, not utilized → failed++
5. **Next query** ranks memories by effectiveness

**If you don't close the loop, arc doesn't learn.**

---

## Guidance Files

For cognitive guidance, read these files from the plugin root:

- `guidance/reason.md` - How to think: impasse detection, complexity assessment, honest uncertainty
- `guidance/act.md` - How to act: verification, scope discipline, honest reporting

These are reference documents, not executable commands.

---

## Session Tracking (Optional)

For multi-task work where you want metacognitive monitoring:

```bash
# Start session
python3 lib/task.py new-session
# → {"session_id": "abc123"}

# After each task, record outcome
python3 lib/meta.py record --session "abc123" --seq 1 --success
python3 lib/meta.py record --session "abc123" --seq 2 --notes "failed because..."

# Check if approach is working
python3 lib/meta.py assess --session "abc123"
```

---

## Summary

| Command | Purpose |
|---------|---------|
| `/arc:recall <q>` | Find relevant memories |
| `/arc:store` | Save failure or pattern |
| `/arc:learn` | Close feedback loop |
| `/arc:chunk` | Extract pattern from success |
| `/arc:health` | System status |
| `/arc:meta` | Is approach working? |
| `/arc:decay` | Show unused memories |
| `/arc:consolidate` | Merge similar |

The intelligence compounds in memory. Use it, report honestly, it gets smarter.
