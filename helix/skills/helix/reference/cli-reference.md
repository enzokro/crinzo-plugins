# CLI Reference

## Memory (9 Core + 2 Code-Assisted)

### Core Primitives

```bash
python3 "$HELIX/lib/memory/core.py" store --type failure --trigger "..." --resolution "..."
python3 "$HELIX/lib/memory/core.py" recall "query" --limit 5 --expand
python3 "$HELIX/lib/memory/core.py" get "memory-name"
python3 "$HELIX/lib/memory/core.py" edge --from "pattern" --to "failure" --rel solves
python3 "$HELIX/lib/memory/core.py" edges --name "memory-name"
python3 "$HELIX/lib/memory/core.py" feedback --names '["mem1", "mem2"]' --delta 0.5
python3 "$HELIX/lib/memory/core.py" decay --days 30 --min-uses 2
python3 "$HELIX/lib/memory/core.py" prune --threshold 0.25 --min-uses 3
python3 "$HELIX/lib/memory/core.py" health
```

### Code-Assisted (surfaces facts, I decide)

```bash
python3 "$HELIX/lib/memory/core.py" similar-recent "trigger" --threshold 0.7 --days 7
python3 "$HELIX/lib/memory/core.py" suggest-edges "memory-name" --limit 5
```

### Maintenance (periodic)

```bash
python3 "$HELIX/lib/memory/core.py" decay-edges --days 60
python3 "$HELIX/lib/memory/core.py" consolidate
python3 "$HELIX/lib/memory/core.py" chunk --task "objective" --outcome "success" --approach "what worked"
```

## Tasks

```bash
python3 "$HELIX/lib/tasks.py" parse-output "$output"
```

## Context

```bash
python3 "$HELIX/lib/context.py" build-lineage --completed-tasks '[...]'
python3 "$HELIX/lib/context.py" build-context --task-data '{...}' --lineage '[...]'
```

## DAG Utilities

```bash
python3 "$HELIX/lib/dag_utils.py" clear
python3 "$HELIX/lib/dag_utils.py" detect-cycles --dependencies '{...}'
python3 "$HELIX/lib/dag_utils.py" check-stalled --tasks '[...]'
```

## Wait Utilities

Zero-context completion polling. **Never use TaskOutput**—use these instead.

```bash
# Instant check (no waiting)
python3 "$HELIX/lib/wait.py" check --output-file "$FILE" --agent-type builder

# Wait with timeout (default 300s)
python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type builder --timeout 300

# Extract structured content from completed output
python3 "$HELIX/lib/wait.py" extract --output-file "$FILE" --agent-type explorer

# Get last JSON block (for explorer findings)
python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"
```

### Agent Types & Markers

| Agent | Markers | Result Location |
|-------|---------|-----------------|
| builder | `DELIVERED:`, `BLOCKED:` | TaskGet metadata |
| explorer | `"status":` | Last JSON in output_file |
| planner | `PLAN_COMPLETE:`, `ERROR:` | TaskList (DAG) |
