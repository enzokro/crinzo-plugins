# Reflection Journal

Chronological observations. What was noticed; what surprised; what remains unclear.

---

## 2026-01-08: anki-v29

**Observed**: 690K tokens (-17.2% from v28). ST=44.5, HT=4.3, IGR=0.91. All 4 tasks complete, 0 fallbacks. Cache efficiency 74.6%.

**Noticed**: Builder 003 hit 154K tokens (vs v28's 286K = -46%). The date-string debugging spiral was AVOIDED. Builder 003 reasoning trace shows "I have clear context. I'll implement the study routes" - action-first, no exploration. Router workspace included "**CRITICAL WARNING - date-string-mismatch**: Use `str(date.today())` for comparison" - the warning was consumed during execution.

**Surprised**: Workspace warning injection WORKED. v28's 286K debugging spiral reduced to v29's 154K clean execution. The intervention we hypothesized in questions.md ("Add known issue warning to 003 workspace") was implemented and delivered -46% token reduction for that task. Runtime knowledge injection is the missing piece.

**Unclear**: Why did cache efficiency drop (74.6% vs 78.8%)? Was this a trade-off for the cleaner execution path?

**Updated**: L011 updated (upfront seeding + workspace warnings = effective). Questions.md prediction confirmed.

---

## 2026-01-08: anki-v28

**Observed**: 834K tokens (+9.9% from v26). ST=48.5 (improved), HT=4.3 (slight degradation from 3.7), IGR=0.92 (slight degradation from 0.93). Cache efficiency 78.8% (down from 80.4%). All 4 tasks complete, 0 fallbacks.

**Noticed**: Builder 003 hit 286K tokens - the date-string debugging spiral PERSISTS despite memory injection fixes. Reasoning trace shows "The database stores dates as strings. I need to convert strings when comparing" - exact same discovery as v23, v26. Knowledge injection at planning time doesn't prevent runtime discovery.

**Surprised**: Token regression despite stable protocol. The date-string pattern is now 4 runs deep (v23: 224K, v26: 227K, v28: 286K). Cross-run learning may need runtime-level intervention, not just upfront knowledge seeding. The builder reads workspace, hits issue during test run, debugs - no opportunity to apply prior knowledge.

**Unclear**: How to prevent runtime debugging spirals? Workspace injection? Pre-computed test fixtures? The pattern occurs AFTER implementation, during verification - outside knowledge seeding window.

**Updated**: N/A (analysis only)

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
