# Exploration Mechanics

## Scope Partitioning Strategies

Identify 3-6 natural partitions based on codebase signals:

| Codebase Signal | Partition Strategy |
|-----------------|-------------------|
| Clear directory structure | One partition per top-level directory |
| Microservices/modules | One partition per service/module |
| Frontend/backend split | Separate partitions for each |
| Framework-organized | Follow framework conventions |
| Monolith with layers | Partition by layer (api, service, data) |

## Required Scopes

**Always include:**
- A `memory` scope for relevant failures/patterns from past sessions
- At least one code scope covering the primary area of change

## Explorer Spawn Pattern

```python
# Inject known facts so explorers skip redundant discovery
explorer_context = python3 "$HELIX/lib/context.py" build-explorer-context \
    --objective "$OBJECTIVE" --scope "$SCOPE"

Task(
    subagent_type="helix:helix-explorer",
    prompt=f"""KNOWN_FACTS:
{json.dumps(explorer_context.get('known_facts', []))}

SCOPE: {scope}
FOCUS: {focus}
OBJECTIVE: {objective}""",
    model="haiku",
    allowed_tools=["Read", "Grep", "Glob", "Bash"],
    run_in_background=True
)
```

## Merging Explorer Outputs

1. Store `output_file` paths when spawning explorers
2. Poll completion: `python3 "$HELIX/lib/wait.py" wait --output-file "$FILE" --agent-type explorer`
3. Extract JSON from completed outputs: `python3 "$HELIX/lib/wait.py" last-json --output-file "$FILE"`
4. Deduplicate files across scopes
5. Resolve conflicts (prefer higher-relevance findings)
6. Aggregate findings preserving `task_hint` for planner grouping
7. Each finding should have: `{file, what, action, task_hint}`

**Why not TaskOutput?** It loads full JSONL transcript (70KB+). The wait utility uses grep (~0 context cost).

## EMPTY_EXPLORATION Recovery

If `targets.files` is empty after merging:

1. Check if scopes were too narrow → broaden
2. Check if objective was unclear → clarify with user
3. Check if codebase is actually empty → verify git ls-files output
4. Consider manual exploration before re-running swarm
