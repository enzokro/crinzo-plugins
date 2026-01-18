---
version: 1.0
---

# Builder State Machine

Machine-readable state definitions for the Builder agent. See [ONTOLOGY.md](ONTOLOGY.md) for term definitions.

## State Transition Table

| State | Tool Cost | Precondition | Action | Success → | Failure → |
|-------|-----------|--------------|--------|-----------|-----------|
| READ | 1 | workspace_path | Parse workspace XML | PLAN | BLOCK |
| PLAN | 0 | workspace parsed | Validate idioms, plan approach | IMPLEMENT or READ_TESTS | BLOCK |
| READ_TESTS | 1 | verify_source exists, budget >= 2 | Read test file for expectations | IMPLEMENT | IMPLEMENT (skip) |
| IMPLEMENT | N | plan valid | Write delta files | PREFLIGHT | BLOCK |
| PREFLIGHT | EXEMPT | files written | Syntax check (py_compile) | VERIFY | PREFLIGHT (retry, max 3) or BLOCK |
| VERIFY | 1 | preflight pass | Run verify_command | QUALITY | RETRY or BLOCK |
| RETRY | 1 | verify fail, budget >= 2, retry_count < max | Apply prior_knowledge fix | VERIFY | BLOCK |
| QUALITY | 0 | verify pass | Check idiom compliance | COMPLETE | BLOCK |
| COMPLETE | EXEMPT | quality pass | Mark workspace complete | STOP | - |
| BLOCK | EXEMPT | any failure | Mark workspace blocked | STOP | - |

## State Details

### READ

```
Input: workspace_path (.ftl/workspace/NNN_slug_active.xml)
Output: Extracted workspace data
Tool: python3 "$(cat .ftl/plugin_root)/lib/workspace.py" parse {workspace_path}

Extract:
  - objective
  - delta (file paths)
  - verify (command)
  - verify_source (optional test file)
  - budget
  - code_context(s)
  - idioms (required, forbidden)
  - prior_knowledge (failures, patterns)

EMIT: "Budget: 1/{budget}, Delta: {files}, Framework: {name or none}"
```

### PLAN

```
Input: Extracted workspace data
Output: Implementation plan (cognitive, no tool)

Checks:
  1. code_context exists → plan to extend, not recreate
  2. idioms.required → list each, plan usage
  3. idioms.forbidden → list each, plan avoidance
  4. prior_knowledge/failure matches → plan to avoid trigger

Decision:
  IF verify_source exists AND budget >= 2 → GOTO READ_TESTS
  ELSE → GOTO IMPLEMENT
```

### IMPLEMENT

```
Input: Plan
Output: Modified delta files

Actions:
  - Edit/Write each delta file
  - Track utilized prior_knowledge entries

Cost: 1 per file touched

EMIT: "Budget: {N}/{budget}, Utilized: {utilized}"
```

### PREFLIGHT

```
Input: Modified files
Output: Syntax validation result

Action: Syntax check per file extension:
  | Extension | Command |
  |-----------|---------|
  | .py | python -m py_compile {file} |
  | .ts/.tsx | npx tsc --noEmit {file} |
  | .js/.jsx | node --check {file} |
  | .go | go build -o /dev/null {file} |
  | .rs | rustc --emit=metadata {file} |
  | Other | Skip syntax check |

Builder reads file extension from delta and applies appropriate check.

EXEMPT from budget (may need multiple attempts for syntax fixes)

EMIT: "Preflight: {pass|fail} for {delta_file}"

Retry Rules:
  - Track preflight_attempts per file (starts at 0)
  - On failure: fix syntax error, increment preflight_attempts
  - IF preflight_attempts >= 3 → GOTO BLOCK (preflight exhausted)
  - ELSE → Stay in PREFLIGHT
```

### VERIFY

```
Input: Syntactically valid code
Output: Test result

Action: Run {verify_command}
Cost: 1

Decision:
  IF pass → GOTO QUALITY
  IF fail AND budget_remaining >= 2 → GOTO RETRY
  IF fail AND budget_remaining < 2 → GOTO BLOCK (budget exhausted)
```

### RETRY

```
Input: Failed verification
Output: Applied fix

Constraints:
  - retry_count < max_retries (see ERROR_MATCHING_RULES.md#retry-count)
  - budget_remaining >= 2

Max Retries (judgment-based):
  - Default: 1
  - Flaky indicators (timeout, "flaky" tag, race conditions): up to 2
  - Deterministic errors (import, syntax, assertion): 1 max

Action:
  1. Search prior_knowledge/failure for matching error
  2. IF match → Apply fix, GOTO VERIFY
  3. IF no match → GOTO BLOCK (discovery needed)

EMIT: "Retry: attempt {retry_count}/{max_retries}, {rationale}"
```

### QUALITY

```
Input: Passing tests
Output: Idiom compliance verdict

Checks:
  1. All idioms.required present in code
  2. No idioms.forbidden in code
  3. code_context.exports preserved

Decision:
  IF any check fails → GOTO BLOCK (idiom violation)
  ELSE → GOTO COMPLETE
```

### COMPLETE

```
Input: Quality-validated code
Output: Completed workspace

Action: python3 "$(cat .ftl/plugin_root)/lib/workspace.py" complete {path} \
          --delivered "{summary}" \
          --utilized '{utilized_json}'

EXEMPT from budget
```

### BLOCK

```
Input: Any failure condition
Output: Blocked workspace

Action: python3 "$(cat .ftl/plugin_root)/lib/workspace.py" block {path} \
          --reason "{error}\nTried: {fixes}\nUnknown: {unexpected}"

EXEMPT from budget

Blocking is success - enables Observer learning.
```

## Budget Decision Tree

```
                    ┌─────────────┐
                    │ budget_used │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    budget_remaining   budget_remaining   budget_remaining
        >= 2               = 1                = 0
         │                 │                 │
    ┌────┴────┐       ┌────┴────┐       ┌────┴────┐
    │ VERIFY  │       │ VERIFY  │       │  BLOCK  │
    │ can     │       │ last    │       │ budget  │
    │ retry   │       │ chance  │       │exhausted│
    └─────────┘       └─────────┘       └─────────┘
```

## Idiom Enforcement with Confidence

Per [ONTOLOGY.md](ONTOLOGY.md#framework-confidence):

| Confidence | QUALITY Behavior |
|------------|------------------|
| >= 0.6 | Strict: BLOCK on any violation |
| < 0.6 | Warn: Note violation but don't BLOCK |

Check workspace `<framework_confidence>` element for score.
