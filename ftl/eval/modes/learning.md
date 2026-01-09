# Learning Mode: Autonomous Planning Anchored by Memory

FTL evaluation in Learning Mode tests whether the orchestrator's planning improves with accumulated memory.

---

## Core Principle: Memory IS the Spec

In Learning Mode, the Planner derives task structure from memory, not from a fixed README template.

| Source | Description |
|--------|-------------|
| **Patterns** | Positive specs: "do this, it works" |
| **Failure Modes** | Negative specs: "don't do this, it breaks" |
| **Learnings** | Meta-specs: "organize work this way" |

The README provides the OBJECTIVE. Memory provides the STRUCTURE.

---

## Comparison: Capability vs Learning Mode

| Aspect | Capability Mode | Learning Mode |
|--------|-----------------|---------------|
| Task structure | Fixed (from README) | Emergent (from memory) |
| Planner role | Transcribe | Derive |
| What's tested | Execution efficiency | Planning intelligence |
| Cross-run comparison | Easy (same structure) | Harder (structure evolves) |
| North Star alignment | Partial | Full |

---

## Learning Mode Flow

```
1. Objective (from user/README)
         ↓
2. Planner reads memory:
   - .ftl/memory/prior_knowledge.md
   - patterns/*.json
   - chronicle.md (learnings)
         ↓
3. Planner DERIVES task structure:
   - Which patterns apply?
   - Which failure modes to warn about?
   - Which learnings inform structure?
         ↓
4. Tasks executed: Router → Builder per task
         ↓
5. Synthesizer extracts patterns from campaign
         ↓
6. Memory updated for next run
```

---

## Planner Reasoning Protocol (Learning Mode)

When in Learning Mode, Planner must show explicit memory reasoning:

```markdown
## Memory Analysis

### Applicable Patterns
Pattern: [name] (signal: [N])
- Components: [list]
- Implication: [how this shapes task structure]

### Failure Mode Warnings
Failure: [name] (impact: [tokens])
- Warn for: [task types]
- Prevention: [what to include in task]

### Structural Learnings
Learning: [ID] - [insight]
- Implication: [how this shapes task structure]

### Derived Task Structure

Given [pattern] + [learning]:

| Task | Type | Derivation |
|------|------|------------|
| ... | ... | [why this task, from which memory] |
```

---

## Structure Quality Metrics

Learning Mode requires new metrics beyond execution efficiency:

| Metric | Calculation | Target |
|--------|-------------|--------|
| pattern_application_rate | tasks with pattern reference / total tasks | >80% |
| failure_avoidance_rate | known failures prevented / known failures applicable | 100% |
| structure_evolution | change in task count/types between runs | Stabilizing over time |
| planning_overhead | planner tokens / total tokens | <10% |
| memory_derivation_ratio | tasks derived from memory / total tasks | >60% |

---

## Evaluation Protocol

### Run Sequence (Learning Mode)

1. **De novo run** (no memory): Planner creates naive structure
2. **Synthesizer captures**: First patterns and failures
3. **Seeded run 1**: Planner derives from memory
4. **Compare**: Structure should improve
5. **Repeat**: Structure should stabilize as memory matures

### What to Measure

**Per-run metrics**:
- Total tokens
- Structure quality (pattern application, failure avoidance)
- Execution quality (action-first, single-attempt)

**Cross-run metrics**:
- Structure evolution (are tasks converging?)
- Memory influence growth (are more patterns being applied?)
- Token reduction (is efficiency improving?)

---

## Example: Anki in Learning Mode

### De Novo (v34 equivalent)
- Planner has no memory
- Creates: implement → implement → implement → test
- Result: ~800K tokens, date-string bug hit

### Seeded Run 1 (v35 equivalent)
- Memory: "tests should precede implementation" (from v34 failure)
- Planner derives: spec-task → implement → implement → verify
- Result: ~600K tokens, still hits date-string bug

### Seeded Run 2 (v36 equivalent)
- Memory: + date-string-mismatch failure mode
- Planner includes warning in data-model task
- Result: ~500K tokens, hits query comparison bug

### Seeded Run 3 (v37 equivalent)
- Memory: + isoformat() for queries
- Planner includes both warnings
- Result: ~450K tokens, clean execution

### Seeded Run 4 (v38 equivalent)
- Memory: Patterns crystallized, high signal
- Planner: Optimal structure
- Result: ~420K tokens, minimal exploration

---

## Implementation Checklist

To run Learning Mode evaluation:

1. [ ] Remove fixed task structure from README (keep objective only)
2. [ ] Ensure memory files exist in `.ftl/memory/`
3. [ ] Use `agents/planner.md` with Learning Mode protocol
4. [ ] Run `eval/instruments/structure_quality.py` on results
5. [ ] Compare structure evolution across seeded runs

---

## Relationship to Capability Mode

Learning Mode is NOT a replacement for Capability Mode.

- **Capability Mode**: "Can FTL execute this spec efficiently?"
- **Learning Mode**: "Does FTL's planning improve with memory?"

Both are needed:
- Capability Mode for benchmarks and regression testing
- Learning Mode for North Star validation

---

## Files

| File | Purpose |
|------|---------|
| `eval/modes/learning.md` | This document |
| `eval/modes/capability.md` | Fixed-structure evaluation (default) |
| `eval/instruments/structure_quality.py` | Learning Mode metrics |
| `agents/planner.md` | Includes Learning Mode reasoning protocol |
