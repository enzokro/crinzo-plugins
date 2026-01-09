# v19 Recommendations from v17 → v18 Analysis

*Generated: 2026-01-08*

## Summary

**v17 → v18: -18.5% tokens** (2.26M → 1.84M)

Builder improvements are strong. Router is the remaining bottleneck.

## Protocol Changes Applied for v19

### 1. router.md - Campaign Flow Constraint

```markdown
**Campaign flow (exactly 4 tool calls)**:
1. Read `.ftl/cache/session_context.md`
2. Read `.ftl/cache/workspace_state.md`
3. Bash `mkdir -p .ftl/workspace`
4. Write workspace file

Your prompt contains: Delta, Depends, Done when, Verify. That IS the workspace content.
Do not gather more context. Create the workspace file from your prompt.
```

### 2. router.md - Explicit Prohibitions

```markdown
**Campaign tasks are pre-scoped by planner. Do NOT:**
- Read source files (main.py, test files) - planner already analyzed them
- Query memory for patterns - planner already incorporated precedent
- Explore with Glob or Grep
- Read completed workspace files for context
```

### 3. Already Applied (from v18)

- **planner.md**: Trust complete input, don't explore when spec in input
- **builder.md**: Cognitive State Check, Write early
- **synthesizer.md**: Trust input paths, act within first 3 reads

## Expected v19 Results

| Agent Type | v18 Avg Tokens | Expected v19 | Reduction |
|------------|----------------|--------------|-----------|
| Planner | 37K | 37K | stable |
| Router | 222K | 60K | -73% |
| Builder | 147K | 120K | -18% |
| Synthesizer | 324K | 200K | -38% |

**Target: 1.0-1.2M total tokens** (from 1.84M)

## Verification

After v19 run:

```bash
python3 info_theory.py ../evidence/runs/anki-v19 --verbose
python3 cognition.py ../evidence/runs/anki-v18 ../evidence/runs/anki-v19
```

Check:
- Router patterns should be `.A` or `..A` (minimal exploration)
- Router tokens should be <100K each
- All builders should show action-first patterns
