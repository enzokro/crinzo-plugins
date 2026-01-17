# Output Templates

This document defines standard output formats shared across FTL agents.

## Explorer Output (JSON)

All explorer modes output JSON directly (no markdown wrapper):

```json
{
  "mode": "{structure|pattern|memory|delta}",
  "status": "{ok|partial|error}",
  // mode-specific fields
}
```

**File Protocol**: Write to `.ftl/cache/explorer_{mode}.json`

## Planner Output

### PROCEED Output

```markdown
### Confidence: PROCEED

## Campaign: {objective}

### Analysis
- Structure: {file_count} files, test_pattern: {pattern}
- Framework: {framework} (confidence: {0-1})
- Prior: {failures} failures, {patterns} patterns
- Complexity: C={score} -> {task_count} tasks

### Tasks
| Seq | Slug | Type | Delta | Verify | Budget |
|-----|------|------|-------|--------|--------|
| 001 | ... | SPEC | ... | ... | 3 |

```json
{plan.json}
```

**Task Graph**:
```
001 (spec) --> 002 (impl) --+
                            +--> 005 (integrate)
003 (spec) --> 004 (impl) --+
```
```

### CLARIFY Output

```markdown
### Confidence: CLARIFY

## Blocking Questions
1. {specific question}

## What I Analyzed
- Structure: {file_count} files
- Framework: {framework}
- Delta candidates: {count} files

## Options
- A: {interpretation} -> {consequence}
- B: {interpretation} -> {consequence}
```

## Builder Output

### On Complete

```markdown
Status: complete
Workspace: .ftl/workspace/NNN_slug_complete.xml
Budget: {used}/{total}

## Delivered
{implementation summary}

## Idioms
- Required: {items used}
- Forbidden: {items avoided}

## Prior Knowledge Utilized
- Patterns: {list}
- Failures avoided: {list}

## Verified
{verify command}: PASS
```

### On Block

```markdown
Status: blocked
Workspace: .ftl/workspace/NNN_slug_blocked.xml
Budget: {used}/{total}

## Discovery Needed
{error symptom}

## Tried
- {fix 1}
- {fix 2}

## Unknown
{unexpected behavior}
```

## Observer Output

```markdown
## Observation Complete

### Mode: TASK | CAMPAIGN

### Automated Foundation
- Workspaces: {complete} complete, {blocked} blocked
- Verified: {confirmed} confirmed, {false_positive} false positives
- Extracted: {failures} failures, {patterns} patterns
- Relationships: {N} auto-linked

### Cognitive Validation
| Decision | Automated | Override | Rationale |
|----------|-----------|----------|-----------|
| Block NNN | CONFIRMED | - | Correct |

### Cognitive Synthesis
**Cross-Workspace Insight:** {insight}
**Systemic Observation:** {theme}
**Knowledge Gap:** {missing}

### Memory State
- Failures: +{N} (automated) +{M} (override)
- Patterns: +{N} (automated) +{M} (override)
- Relationships: +{N} (automated) +{M} (discovered)
- Feedback: {N} helped, {M} failed

### Prediction
{likely future issues}

Budget: {used}/10
```

## EMIT Statement Format

All agents emit state transitions:

```
EMIT: "{key}: {value}, {key2}: {value2}"
```

Examples:
- `EMIT: "State: PLAN, Status: coherence check"`
- `EMIT: "Budget: 3/5, Action: edited lib/auth.py"`
- `EMIT: "Phase: validation, Status: reviewing 3 blocks"`
