# Reflection Journal

Chronological observations. What was noticed; what surprised; what remains unclear.

---

## 2026-01-08: anki-v26

**Observed**: 759K tokens (+6.6% from v24). ST=46.6 (improved), HT=3.7 (improved), IGR=0.93 (improved). Cache efficiency 80.4% (best yet). All 4 tasks complete, 0 fallbacks.

**Noticed**: Better epiplexity metrics but higher token cost. Builder 003 hit 227K - same date-string debugging spiral as v23. Memory was seeded to `.ftl/memory/` but transcript shows NO agent read it.

**Surprised**: Protocol changes to planner.md and router.md (adding "Prior Knowledge" sections) were ineffective. Agents don't execute bash snippets in markdown. The descriptive protocol ≠ prescriptive behavior. Memory injection requires orchestrator-level changes.

**Unclear**: None - root cause identified and fixed.

**Updated**: SKILL.md (inject prior_knowledge.md into session_context and planner prompts), meta_eval.sh (added --info-theory flag to capture.py)

---

## 2026-01-08: anki-v24

**Observed**: 711K tokens. All 4 routers hit exact 4-call sequence. Builders show "I have a clear picture" first thoughts. Task 003 dropped from 224K to 151K (-32%).

**Noticed**: Entropy dropped 12% (HT: 5.0→4.4). The "Delivered section" fix from v23 propagated - builders now edit workspace before completion.

**Surprised**: Sequential task routing (v23 change) paid off here - knowledge from earlier tasks prevented the date-string debugging spiral that hit v23.

**Unclear**: Why does planner still do 5 tool calls when spec is complete? Should be 0-1.

**Updated**: builder.md (Delivered persistence), router.md (pattern warnings in Thinking Traces)

---

## 2026-01-08: anki-v23

**Observed**: 783K tokens (-35% from v22). Ontological refactor delivered. Zero fallbacks (v22 had 1). Router compliance 3/4 perfect.

**Noticed**: The "single decision point" framing worked - agents ask one question then branch. Category tests ("Am I about to explore?") caught anti-patterns.

**Surprised**: Builder 003 still hit 224K due to date-string-mismatch debugging. The failure mode wasn't warned about in workspace.

**Unclear**: How to propagate failure mode knowledge to future runs? (Led to cross-run learning design)

**Updated**: All four agent protocols rewritten with ontological structure

---

## 2026-01-08: anki-v22

**Observed**: 1.21M tokens (+6.5% REGRESSION from v21). Synthesizer hit fallback (249K, +55%). Incremental patches backfired.

**Noticed**: Protocols had contradictory guidance - "Trust complete input" coexisted with "Project Verification Landscape" exploration commands. Agents executed BOTH paths.

**Surprised**: Builder 002 improved (-36%) with targeted "Debugging vs Exploration" fix, but everything else regressed. Focused changes work; accumulated patches confuse.

**Unclear**: How to refactor without regression? (Led to ontological refactor plan)

**Updated**: Incremental patches reverted; full refactor planned

---

## 2026-01-08: anki-v21

**Observed**: 1.14M tokens. Baseline for ontological refactor. Planner said "PROCEED" but still did 5 tool calls. Builder 002 hit 211K (date debugging). Builder 003 hit 313K (test naming).

**Noticed**: First thoughts revealed cognitive state. Efficient: "I have a clear picture." Inefficient: "Let me look at Y to understand..."

**Surprised**: The 313K builder traced back to planner error - `-k study` filter didn't match test names. Builder can't fix planner mistakes.

**Unclear**: How to make verification coherent? (Added filter rule to planner)

**Updated**: Documented as baseline; no protocol changes

---

## Template

```
## YYYY-MM-DD: [run-id]

**Observed**: What happened
**Noticed**: What stood out
**Surprised**: What defied expectation
**Unclear**: What remains unresolved
**Updated**: Which files changed
```

---
