# FTL Evaluation Chronicle

Learnings compound into FTL's decision memory via `./eval.sh integrate`.

---

## 2026-01-09: v28-v32 Meta-Pattern Analysis

**Change**: Analyzed 5 runs to extract generalizable orchestration patterns
**Result**: Identified 6 meta-patterns that apply to ANY FTL campaign

### Key Findings

**L003**: Trace pattern predicts cost
- `AAA` (all action) is most efficient; each `.` (deliberation) adds ~10-15K tokens
- Trace length is proxy for workspace quality
- Action-first (`A` at position 0) correlates with lower cost

**L004**: Task type determines pipeline
- BUILD tasks need full router→builder pipeline
- VERIFY tasks only need single command execution (88K savings in v32)
- Task classification should happen before workspace creation

**L005**: Memory availability ≠ memory influence
- v28: Memory was available but not consumed
- v29+: Memory consumed (no date-string spiral) but cache_effective=0
- Need to measure explicit pattern references in reasoning traces

**L006**: Agent type should be determined by behavior, not spawn order
- First reads + first tool call = behavioral signature
- Planner: Reads README/spec, outputs "PROCEED" or task breakdown
- Direct: Single Bash tool call, verification task

### Protocol Changes Implemented

1. router.md: Added task classification (BUILD vs VERIFY)
2. builder.md: Added NO RECAP instruction (action-first)
3. capture.py: Added behavioral type detection
4. info_theory.py: Added memory_influence_rate and action_first_rate metrics

### New Orchestration Metrics

| Metric | Calculation | Target |
|--------|-------------|--------|
| action_first_rate | builders with trace[0]='A' / total | >80% |
| memory_influence_rate | explicit pattern refs / total traces | >50% |
| average_trace_length | sum(traces) / agents | <3 |

---

## 2026-01-08: v28 Memory Injection Fix

**Change**: campaign.sh now calls session_context.sh before Claude starts
**Result**: v28 (834K) → v29 (690K) = 17% improvement; date-string spiral eliminated

**L002b**: Shell pre-hooks > embedded markdown bash blocks
- SKILL.md bash code blocks are descriptive, not executed
- Shell scripts run before agent reasoning = guaranteed context injection

---

## 2026-01-07: Harness Refinement — Main Session Integration

**Change**: collect.sh now captures main orchestrator session; capture.py parses spawn chain
**Result**: spawn_graph populated from authoritative source; spawn_sequence shows complete orchestration

**L002**: Main session contains spawn authority
- Agent logs are children, not parents
- Task tool calls in orchestrator define spawn relationships
- File mtime is unreliable; main session order is ground truth

---

## 2026-01-06: anki-v12 — Ontology Refactor

**Change**: "Two Workflows" section added to SKILL.md
**Result**: 0 learners (vs 5 in v10), -18% tokens, 100% protocol fidelity

**L001**: Ontological framing > imperative prohibition
- Prohibition ("DO NOT") fails; category error framing succeeds
- Mechanism: "X is incoherent" removes X from decision space; "don't do X" requires suppressing X
- Generalizes: frame constraints as structural impossibilities, not policy rules

---

## Learnings Index

| ID | Insight | Signal |
|----|---------|--------|
| L001 | Ontological framing > imperative prohibition | +3 |
| L002 | Main session contains spawn authority | +3 |

---
