# Reflection Journal

Chronological observations. What was noticed; what surprised; what remains unclear.

---

## 2026-01-09: anki-v34

**Observed**: 671K tokens (+6.8% from v33 - first regression after stable run). ST=42.8, HT=3.4, IGR=0.93. 3/3 builder tasks complete, 0 fallbacks. Cache efficiency 76.9% (essentially flat). Protocol fidelity: single_planner=false, single_synthesizer=false (same "deviant" pattern as v32).

**Noticed**: Token regression across ALL task flows: 001=100K (v33=87K, +15%), 002=141K (v33=133K, +6%), 003=248K (v33=198K, +25%), 004=59K (v33=45K, +31%). The same synthesizer-as-planner pattern that worked in v32 (-16.2%) caused regression in v34 (+6.8%). Entropy dropped sharply from 4.7 to 3.4 - returning to the "low entropy" band after v33's anomalous spike. Two synthesizers spawned: one at start (24K tokens, planning role), one at end (98K tokens, pattern extraction).

**Surprised**: Protocol deviation inconsistency. v32's synthesizer-as-planner achieved -16.2% improvement. v34's identical pattern achieved +6.8% regression. The protocol pattern is not deterministic of outcome - other factors dominate. Entropy drop (4.7→3.4) occurred despite protocol deviation, inverting the v33 observation that "proper protocol = more entropy."

**Unclear**: Why did the same protocol deviation work in v32 but regress in v34? Candidates: (1) random variance in LLM outputs, (2) subtle prompt differences in orchestrator, (3) warm cache effects in v32 that v34 lacked. The 25% regression in task 003 (routes-study) is particularly puzzling since workspace warnings are still active.

**Updated**: N/A

---

## 2026-01-09: anki-v33

**Observed**: 628K tokens (-0.7% from v32 - essentially flat). ST=42.9, HT=4.7, IGR=0.9. 4/4 tasks complete, 0 fallbacks. Cache efficiency 77.2% (up from 72.9%). Protocol fidelity improved: single_planner=true, single_synthesizer=true (v32 had both false).

**Noticed**: Protocol structure restored but no efficiency gain. v32's "deviant" approach (synthesizer-as-planner, 2 synthesizers) was NOT inferior - v33's proper protocol achieved same token cost. Task flows improved for early tasks: 001=87K (v32=115K, -24%), 002=133K (v32=150K, -11%). But task 003=198K (v32=189K, +5%). Entropy jumped significantly: HT=4.7 vs v32's HT=3.4 (+38%). Router cache rate remains 100% effective.

**Surprised**: Entropy spike to 4.7 breaks the bimodal hypothesis. Previous pattern: v30=3.4, v31=4.4, v32=3.4 suggested two stable states. v33's 4.7 is the highest entropy observed in recent runs. Yet execution was clean (0 fallbacks, all single-attempt). High entropy + clean execution suggests entropy measures something other than execution stability.

**Unclear**: What caused the entropy spike? v33 has cleaner protocol fidelity but higher entropy than v32. Possible: HT measures variance in agent behavior patterns, not execution quality. The restored protocol may introduce more variance in how agents approach tasks (more "proper" separation of concerns = more behavioral diversity).

**Updated**: N/A

---

## 2026-01-09: anki-v32

**Observed**: 632K tokens (-16.2% from v31). ST=42.8, HT=3.4, IGR=0.93. 3/4 tasks marked complete in metrics (task 004 used "unknown" agent type). 0 fallbacks. Cache efficiency 72.9%. Protocol fidelity deviated: single_planner=false (synthesizer did planning), single_synthesizer=false (2 synthesizers spawned).

**Noticed**: Builder 003 (routes-study) continued improving: 148K tokens (vs v31's 162K = -8.6%). Workspace warning pattern still effective. Task 004 was ultra-efficient: only 18K tokens with 1 tool call (just ran pytest verify). The run used fewer agents (9 vs 10) and fewer API calls (78 vs 91). Token efficiency improved across all tasks: 001=115K (vs 102K +13%), 002=150K (vs 140K +7%), 003=189K (vs 201K -6%), 004=18K (vs 105K -83%). The dramatic 004 improvement suggests verification-only tasks can be streamlined.

**Surprised**: ST dropped (42.8 vs 46.0) while tokens dropped -16.2%. Usually higher ST correlates with efficiency. This suggests ST may measure structure independent of efficiency gains. Also surprised that protocol deviations (no dedicated planner) didn't cause regression - the double-synthesizer approach actually worked.

**Unclear**: Why did ST drop? Is the epiplexity metric sensitive to agent composition (fewer agents = lower ST)? Why did entropy hit 3.4 again (same as v30)? Two data points at HT=3.4 vs v31's HT=4.4 suggests bimodal behavior rather than continuous noise.

**Updated**: N/A

---

## 2026-01-09: anki-v31

**Observed**: 755K tokens (+8.5% from v30 - first regression after 2 stable runs). ST=46.0, HT=4.4, IGR=0.91. All 4 tasks complete, 0 fallbacks. Cache efficiency 74.8%. Protocol fidelity perfect (single_planner, single_synthesizer, router_cache_rate=1.0).

**Noticed**: Builder 003 (routes-study) regressed: 162K tokens vs v30's 126K (+28%). This is the same task that hit 154K in v29 and 286K in v28. The workspace warning pattern is still active, so this isn't a return to the debugging spiral - the reasoning traces still show "I have a clear picture" action-first patterns. The extra tokens appear to be in Edit operations (5 edits in v31 vs 2 in v30) - more iterative refinement rather than debugging.

**Surprised**: v30's entropy drop (HT=3.4) reversed to HT=4.4 in v31. This confirms the v30 journal hypothesis - the drop WAS measurement noise, not genuine variance reduction. Entropy is inherently noisy in the 4-4.5 range for stable campaigns.

**Unclear**: Why did builder 003 need 5 edits instead of 2? Both runs had the same workspace specification. Possible factors: (1) random variation in LLM output, (2) subtle prompt differences, (3) test file state differences. Not concerning unless pattern persists.

**Updated**: questions.md (entropy question resolved)

---

## 2026-01-08: anki-v30

**Observed**: 695K tokens (+0.7% from v29 - stable). ST=46.2, HT=3.4, IGR=0.93. All 4 tasks complete, 0 fallbacks. Cache efficiency 76.5%. Protocol fidelity restored (single_planner=true, vs v29's false).

**Noticed**: Builder 003 (routes-study) continued improving: 126K tokens (vs v29's 154K = -18%). Workspace warning pattern compounding. All builders show "I have a clear picture" first thoughts - action-first cognitive state is now standard. Planner properly typed (was "unknown" in v29). Entropy dropped from 4.3 to 3.4 - system becoming more deterministic.

**Surprised**: None. This is expected stability - the workspace warning pattern established in v29 continues to deliver. Token count flat but quality metrics improved across all dimensions (ST↑, HT↓, IGR↑). The system is doing the same work with better structure.

**Unclear**: Why did HT drop so significantly (4.3 → 3.4)? Is this measurement noise or genuine variance reduction? Worth watching in v31.

**Updated**: N/A (stable run, no protocol changes needed)

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
