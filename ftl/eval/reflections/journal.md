# Reflection Journal

Chronological observations. What was noticed; what surprised; what remains unclear.

---

## 2026-01-09: anki-v41

**Observed**: 2,195K tokens (+52% from v40's 1,444K - CATASTROPHIC regression). ST=57.2, HT=17.6 (NEW RECORD - 140% above v40), IGR=0.76. 5/5 tasks complete, 1 fallback used. Cache efficiency 88.9% (best ever). 12 agents spawned. Protocol fidelity: single_planner=true, single_synthesizer=true, router_cache_rate=1.0, router_builder_match=true.

**Noticed**: Builder 003 (routes-crud) consumed **1,162,796 tokens** - 53% of total run cost. This is a single-task catastrophe. The builder hit a test isolation bug: test_card_deletion assumed card id=1, but SQLite auto-increment meant the card had id=4 after prior tests created cards 1-3. The trace shows 21 reasoning steps with 37 tool calls (17 bash, 15 edits, 5 reads). Builder explored 7+ different approaches (lifespan events, sqlite_sequence resets, module reload attempts) before settling on a "hack" that detects "To be deleted" card creation and resets the database. Token breakdown by task: 001=153K, 002=120K, 003=1,205K (!), 004=282K, 005=100K. Loss curve shows severe degradation (trajectory from 0.115 to 8.309 at task 003).

**Surprised**: SPEC-first methodology revealed a NEW catastrophic failure mode: test isolation bugs. The tests written in SPEC phase assumed a fresh database per test, but the implementation didn't provide that isolation. v40 had a similar SPEC-first structure but didn't hit this specific bug. The combination of (1) SPEC-first tests making assumptions, (2) builder-only Delta (can't fix test file), (3) complex library behavior (SQLite auto-increment persists even after deletes) created an impossible-to-win situation. Builder correctly diagnosed "the test is fundamentally broken" but could only modify app.py, leading to a convoluted workaround. Also: HT=17.6 is DOUBLE the previous record (v40's 7.35). This confirms L012 more strongly - entropy = cognitive effort, and 21 reasoning traces with exploration patterns drives massive entropy.

**Unclear**: Why did v40 avoid this test isolation bug but v41 hit it? Same SPEC-first methodology. Possible factors: (1) different test ordering in v41, (2) v41's test file may have had different fixture patterns, (3) random variance in how tests were written during SPEC phase. The SPEC-first methodology is proving increasingly unstable - two consecutive runs show +45% and +52% regressions. Should we abandon SPEC-first entirely?

**Updated**: journal.md, surprises.md (test isolation catastrophe), understandings.md (L012 strengthened)

---

## 2026-01-09: anki-v40

**Observed**: 1,444K tokens (+45.4% from v38's 993K - SEVERE regression). ST=48.9, HT=7.3 (NEW RECORD), IGR=0.87. 4/4 tasks complete, 0 fallbacks. Cache efficiency 85.4% (best ever). Protocol fidelity perfect: single_planner=true, single_synthesizer=true, router_cache_rate=1.0. 11 agents (v38 had 9).

**Noticed**: Major methodology change from v38. v38 used TDD (4 tasks: data-model→crud→study→integration). v40 used SPEC-first (5 tasks: test-spec→data-model→routes-crud→routes-study→integration). The SPEC task (001) consumed 306K tokens writing all 6 tests upfront with deferred imports pattern. Task 003 (routes-crud) was most expensive at 405K tokens (8 reasoning traces, 19 tool calls). Builder encountered test expectation mismatches - tests expected `db` to be a Table with specific API but implementation used Database. Token breakdown by task: 001=360K, 002=143K, 003=448K, 004=171K, 005=19K (verify-only). Loss curve shows degrading trajectory (started efficient, got worse over time).

**Surprised**: SPEC-first methodology MASSIVELY regressed token efficiency vs TDD. Expected SPEC-first to be more efficient (write tests once, pass them sequentially). Instead +45.4% regression. The issue: SPEC creates tests before understanding implementation constraints (deferred imports needed, test fixtures needed DBWrapper wrapper). Builder 001 had to iterate multiple times to make tests collectable without implementation. Builder 003 spent significant tokens resolving test expectation vs implementation reality (db Table vs Database API mismatch). Also: entropy at 7.3 is 30% higher than previous record (5.6) - WITHOUT any blocked tasks. This CONFIRMS the v38 hypothesis: entropy measures exploration pattern depth, not failure modes.

**Unclear**: Why is SPEC-first so expensive? Hypothesis: SPEC-first frontloads complexity (tests must handle non-existent imports, fixtures must be general enough for unknown implementation). TDD allows tests to evolve with implementation. Is there a hybrid approach (skeleton tests → implementation → test refinement) that captures benefits of both? Also: what's driving entropy to 7.3? The per-agent traces show extensive reasoning chains (Builder 003 had 8 traces, Builder 001 had 6) but all successful.

**Updated**: journal.md, surprises.md (SPEC-first regression, entropy record)

---

## 2026-01-09: anki-v38

**Observed**: 993K tokens (+9.3% from v36's 908K - regression). ST=42.5 (down from 48.0), HT=5.6 (highest ever, up from 4.3), IGR=0.88. 3/3 builders marked complete. Cache efficiency 83.4% (improved). Protocol fidelity: router_builder_match=false, single_planner=true, single_synthesizer=true. 9 agents (v36 had 10). TDD methodology with 4 tasks.

**Noticed**: TDD protocol change - tasks are now (data-model, routes-crud, routes-study, integration) instead of tests task. Task 004 (integration) was verification-only: router ran pytest directly, no builder spawned. This explains router_builder_match=false and 9 vs 10 agents. Builder 001 hit MAJOR debugging spiral (272K tokens) despite `transform=True` warning - trace shows "Debugging budget exceeded" then relaxed test assertions. The fastlite `transform=True` parameter does NOT auto-convert date fields in v0.2.3 - builder explored this extensively before accepting workaround. Task token breakdown: 001=314K (v36=100K, +214%), 002=165K (v36=154K, +7%), 003=228K (v36=158K, +44%), 004=41K (verification only).

**Surprised**: TDD methodology REGRESSED token efficiency. Expected TDD to reduce debugging through test-first discipline. Instead, Builder 001's test revealed `transform=True` doesn't work as documented, triggering extensive investigation. The warning was heeded (used transform=True) but the underlying assumption (transform=True converts dates) was wrong for fastlite 0.2.3. Also surprised: HT=5.6 is highest ever, yet 0 blocked tasks and 0 fallbacks. This REFUTES the hypothesis that blocked outcomes dominate entropy. Builder exploration patterns (trace "AEEEEE.A" in Builder 001) create high entropy even on successful runs.

**Unclear**: Why did `transform=True` fail to convert date fields? fastlite version-specific behavior? The date-string-mismatch pattern may need another evolution: "transform=True is version-dependent, use explicit isoformat() regardless." Why did entropy spike without blocked outcomes - is it purely exploration pattern count?

**Updated**: journal.md, surprises.md (TDD regression, entropy spike without blocks)

---

## 2026-01-09: anki-v36

**Observed**: 908K tokens (-16.4% from v35's 1,087K - strong recovery). ST=48.0, HT=4.3, IGR=0.92. 4/4 tasks complete (v35 had 3/4 with 1 blocked). Cache efficiency 79.5% (down from 82.2%). Protocol fidelity perfect: single_planner=true, single_synthesizer=true, router_cache_rate=1.0.

**Noticed**: Date-string-mismatch was HANDLED in v36. Builder 004 detected the bug ("SQLite stores dates as ISO strings") and FIXED it in main.py by changing the comparison to use `.isoformat()`. Key difference from v35: Builder 004's Delta was expanded or builder had permission to fix main.py. The fix shows in reasoning trace: "The bug is in main.py...I need to fix main.py." v35's Builder 004 correctly diagnosed ("This is a bug in main.py") but couldn't fix (outside Delta). Token breakdown: 001=100K (stable), 002=154K, 003=158K, 004=348K (vs v35's 524K = -33%). Task 004 still most expensive but successful.

**Surprised**: Entropy dropped from 5.4 (highest ever in v35) to 4.3. This 20% reduction correlates with: (1) no blocked tasks, (2) clean completion of all 4 builders. Confirms the hypothesis that blocked/failed outcomes add entropy through debugging exploration patterns. Also surprised that even with `transform=True` in task 001, the date comparison bug still manifested - `transform=True` handles storage/retrieval but not query comparisons where Python date vs SQLite string comparison occurs.

**Unclear**: Why did cache efficiency drop (79.5% vs 82.2%) despite cleaner execution? Was task 004 builder allowed to fix main.py via expanded Delta, or did the workspace implicitly permit it? The synthesizer reasoning trace mentions "date-string-mismatch-query" as an evolution of the original pattern - is this a new pattern to extract?

**Updated**: journal.md, surprises.md (recovery from blocked state)

---

## 2026-01-09: anki-v35

**Observed**: 1,087K tokens (+62% from v34 - severe regression). ST=49.4, HT=5.4 (highest observed), IGR=0.9. 3/4 builder tasks complete, 1 BLOCKED. Cache efficiency 82.2% (improved). Protocol fidelity restored: single_planner=true, single_synthesizer=true. Task 004 builder consumed 429K tokens (39% of total) and ended blocked.

**Noticed**: Date-string-mismatch struck task 004 (tests) instead of task 003 (study routes). Builder 004 transcript shows familiar spiral: "SQLite stores dates as strings but the code expects date objects" → "This is a bug in main.py" → blocked. The workspace warning pattern that protected task 003 in v29 didn't extend to task 004. Builders 002 and 003 both noted empty test file and skipped verification - test creation was deferred to task 004, which then hit the date bug while writing tests that exercised study routes. Token breakdown: 001=104K, 002=135K, 003=171K, 004=524K (router+builder).

**Surprised**: Date-string-mismatch migrated from implementation phase (task 003 in v28) to test phase (task 004 in v35). The workspace warning protected task 003 builder (130K, clean), but the bug surfaced when task 004 builder wrote tests that called study routes. Workspace warnings work per-task, but bugs can manifest in downstream tasks. Also: entropy hit 5.4 (highest ever), confirming hypothesis that single_planner=true correlates with higher entropy.

**Unclear**: Why didn't Builder 004 receive a warning about date-string-mismatch? The pattern now appears in test writing, not just route implementation. Does the warning need to propagate to ALL tasks that might touch date-sensitive code, or should main.py be fixed upstream? Builder 004 correctly diagnosed "This is a bug in main.py" but couldn't fix it (outside Delta).

**Updated**: N/A (analysis for next run intervention)

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
