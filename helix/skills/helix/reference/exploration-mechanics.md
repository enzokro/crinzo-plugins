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

Spawn explorers using XML syntax (no `allowed_tools` needed—agents use frontmatter):

```xml
<invoke name="Task">
  <parameter name="subagent_type">helix:helix-explorer</parameter>
  <parameter name="prompt">SCOPE: src/api/
FOCUS: route handlers
OBJECTIVE: {objective}</parameter>
  <parameter name="model">haiku</parameter>
  <parameter name="max_turns">8</parameter>
  <parameter name="run_in_background">true</parameter>
  <parameter name="description">Explore src/api</parameter>
</invoke>
```

## Merging Explorer Outputs

SubagentStop hook writes each explorer's findings to `.helix/explorer-results/{agent_id}.json`. Use the batch wait utility:

```bash
python3 "$HELIX/lib/wait.py" wait-for-explorers --count $EXPLORER_COUNT --timeout 120
```

Returns JSON with `completed`, `findings` (merged, deduped by file path), and partial results on timeout.

**Why not TaskOutput?** It loads full JSONL transcript (70KB+). The wait utility polls small JSON files (~0 context cost).

## EMPTY_EXPLORATION Recovery

If `targets.files` is empty after merging:

1. Check if scopes were too narrow → broaden
2. Check if objective was unclear → clarify with user
3. Check if codebase is actually empty → verify git ls-files output
4. Consider manual exploration before re-running swarm
