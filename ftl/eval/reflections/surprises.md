# Surprises

Gaps between prediction and reality. These reveal where mental models are wrong.

---

## 2026-01-09: SPEC-first methodology caused SEVERE regression (+45%)

**Expected**: SPEC-first methodology (write all tests upfront in task 001, then implement sequentially) should be more efficient than TDD by eliminating redundant test-write cycles and providing clear targets for each build task.
**Observed**: v40 used SPEC-first and consumed 1,444K tokens (+45.4% from v38's 993K TDD run). Task 001 (test-spec) alone consumed 306K tokens to write tests without implementation. Task 003 (routes-crud) consumed 405K tokens debugging test expectation vs implementation mismatches.
**Gap**: SPEC-first frontloads complexity to the wrong phase. Writing tests before implementation forces tests to handle: (1) non-existent imports (deferred import pattern), (2) unknown implementation details (DBWrapper needed for test API compatibility), (3) fixture design without knowing actual data structures. TDD's incremental approach allows tests to co-evolve with implementation. The mental model "write tests once, pass them efficiently" ignores the cost of writing tests that must anticipate unknown implementation constraints. SPEC-first may work when implementation is fully specified; for exploratory builds it AMPLIFIES costs.
**Updated**: journal.md

---

## 2026-01-09: Entropy hit 7.3 - 30% above previous record

**Expected**: Based on v38's HT=5.6 being the highest observed (with 0 blocked tasks), v40's clean execution (4/4 complete, 0 fallbacks) should have HT in the 4-6 range.
**Observed**: v40 achieved HT=7.35 - 30% above the previous record. Entropy components show variance=7.35 as the dominant factor. No retries, no fallbacks.
**Gap**: This STRONGLY CONFIRMS the v38 hypothesis that entropy measures exploration pattern depth, not failure modes. v40's builders had extensive reasoning chains: Builder 003 had 8 traces (trace pattern "A......A"), Builder 001 had 6 traces (trace pattern "AE...A"). The SPEC-first methodology required more exploration because tests were written without implementation context. Updated entropy model: **HT ≈ sum(per_agent_reasoning_trace_count) × complexity_factor**. Entropy is NOT capped by task success - it measures cognitive effort regardless of outcome.
**Updated**: questions.md (entropy hypothesis confirmed)

---

## 2026-01-09: TDD methodology INCREASED token cost

**Expected**: TDD (test-first) methodology would reduce debugging by catching issues early through failing tests, leading to lower total token consumption.
**Observed**: v38 used TDD methodology and consumed 993K tokens (+9.3% from v36's 908K). Builder 001 hit 272K tokens (vs v36's 59K = +361%) despite writing test first. The test revealed `transform=True` doesn't auto-convert date fields in fastlite 0.2.3, triggering investigation spiral.
**Gap**: TDD catches bugs early but doesn't reduce debugging cost when the bug is in third-party library behavior rather than application logic. Builder 001 followed TDD correctly: wrote test, ran test, saw failure. But the failure pointed to library behavior (fastlite transform=True), not implementation error. This led to extensive exploration of fastlite internals before accepting workaround. TDD is efficient for application bugs; it may AMPLIFY costs for library/framework bugs by surfacing them in test phase rather than integration phase. The mental model "TDD reduces debugging" needs refinement: "TDD shifts bug discovery earlier; cost depends on bug source."
**Updated**: journal.md

---

## 2026-01-09: Entropy spiked to 5.6 without blocked tasks

**Expected**: Based on v36 analysis, entropy (HT) correlates primarily with blocked/failed outcomes. v38 with 0 blocked tasks and 0 fallbacks should have HT in 3.4-4.5 range.
**Observed**: v38 achieved HT=5.6 - highest ever observed - with 0 blocked tasks and 0 fallbacks. All 3 builders completed successfully.
**Gap**: Entropy is NOT dominated by blocked outcomes. Builder 001's exploration pattern "AEEEEE.A" (action, then 5 explores, then action) shows high behavioral variance on a successful task. The trace shows 8 reasoning steps with 5 exploration-marked segments. Entropy measures variance in agent behavior patterns, not just failure modes. The hypothesis "blocked outcomes dominate entropy" is REFUTED. Updated model: **Entropy = f(exploration_pattern_depth, blocked_outcomes)** where exploration patterns can dominate even without failures.
**Updated**: questions.md (entropy hypothesis needs revision)

---

## 2026-01-09: transform=True heeded but still failed

**Expected**: The date-string-mismatch warning instructing `transform=True` in db.create() would prevent date-related bugs. v38 should execute cleanly with this warning.
**Observed**: v38 Builder 001 correctly used `transform=True` as instructed. Test still failed because fastlite 0.2.3 doesn't actually auto-convert date fields with this parameter. Builder reasoning: "transform=True isn't working as expected... fastlite 0.2.3 transform=True does not auto-convert date fields."
**Gap**: The warning was CORRECT (use transform=True) but INCOMPLETE for this fastlite version. `transform=True` behavior is version-dependent. The pattern needs evolution: original (use transform=True) → v36 evolution (also use .isoformat() in queries) → v38 evolution (transform=True may not work at all in some versions; ALWAYS use explicit string handling). The mental model "following the warning prevents the bug" assumes the warning captures all conditions. Library version variance can invalidate correct warnings.
**Updated**: N/A (synthesizer should capture this evolution)

---

## 2026-01-09: Builder CAN fix upstream bugs when detected during testing

**Expected**: Based on v35, believed builders with test-writing Delta couldn't fix bugs in implementation files (main.py). v35 Builder 004 diagnosed "This is a bug in main.py" but ended BLOCKED, unable to fix.
**Observed**: v36 Builder 004 detected same bug and FIXED main.py (line 52: changed `date.today()` to `date.today().isoformat()` for query comparison). Completed in 307K tokens vs v35's 429K blocked.
**Gap**: The constraint isn't hard. Either: (1) v36's workspace/Delta was more permissive, allowing main.py edits during test writing, (2) the builder interpreted "test writing" more liberally when bug discovery required upstream fix, or (3) task 004's framing changed between v35/v36 to allow implementation fixes discovered via testing. The mental model "builders can only modify Delta" may be too rigid - effective builders can expand scope when necessary for task completion. This is a positive surprise: flexible scoping enabled recovery.
**Updated**: journal.md

---

## 2026-01-09: transform=True is necessary but insufficient for date comparisons

**Expected**: The date-string-mismatch warning instructing `transform=True` in db.create() would prevent all date-related bugs. v35's problem was task 003 not using transform=True.
**Observed**: v36 task 001 correctly used `transform=True`. Bug still manifested in task 004 tests. The issue: `transform=True` handles storage/retrieval (dates round-trip correctly) but NOT query comparisons where `c.next_review <= date.today()` compares SQLite string to Python date. Fix required: `date.today().isoformat()` in query expressions.
**Gap**: The pattern warning was incomplete. `transform=True` prevents STORAGE bugs; query comparisons need explicit `.isoformat()` on Python date variables. The synthesizer correctly identified this as "date-string-mismatch-query" - an evolution of the original pattern. Pattern needs refinement to include both prevention mechanisms.
**Updated**: N/A (synthesizer captured the evolution)

---

## 2026-01-09: Entropy correlates with blocked/failed outcomes

**Expected**: Entropy (HT) would remain elevated in v36 since v35's HT=5.4 was attributed to single_planner=true pattern.
**Observed**: v36 had single_planner=true (same as v35) but HT dropped from 5.4 to 4.3 (-20%). Key difference: v35 had 1 blocked builder; v36 had 0 blocked.
**Gap**: Entropy is more strongly correlated with blocked/failed outcomes than protocol composition. v35's blocked Builder 004 (429K tokens, debugging exploration patterns) inflated entropy. v36's successful Builder 004 (307K tokens, clean completion) reduced entropy. The mental model "single_planner → high entropy" is incomplete; it's "single_planner + blocked outcomes → highest entropy."
**Updated**: questions.md (entropy hypothesis update)

---

## 2026-01-09: Date-string-mismatch migrated to test phase

**Expected**: Workspace warnings for task 003 (study routes) would contain the date-string-mismatch problem as in v29. Task 004 (tests) would be lightweight verification.
**Observed**: v35 Task 003 completed cleanly in 130K tokens. Task 004 builder wrote tests that exercised study routes and hit the date-string-mismatch bug, consuming 429K tokens and ending BLOCKED. Total run: 1.087M tokens (+62% regression).
**Gap**: Workspace warnings protect the task they're attached to, not downstream tasks that interact with the code. The bug was in main.py (created by task 003), but task 003 builder never ran tests (empty test file). Task 004 builder couldn't fix main.py (outside its Delta). The warning mechanism needs to propagate to ANY task whose tests touch date-sensitive code, OR main.py needs to be fixed with `transform=True` in task 001/003. Current mitigation is per-task; bug manifestation is cross-task.
**Updated**: journal.md, questions.md

---

## 2026-01-09: Entropy breaks 5.0 for first time

**Expected**: Entropy would remain in observed range (3.4-4.7). Pattern suggested single_planner=true → higher entropy (~4.4-4.7), single_planner=false → lower entropy (~3.4).
**Observed**: v35 achieved HT=5.4 with single_planner=true - highest observed value, 15% above previous max (4.7).
**Gap**: Entropy is not capped by execution quality. v35 had clean protocol fidelity but extremely high entropy. The blocked task 004 builder (429K tokens, 7 reasoning traces, exploration pattern "A.E.E..") likely contributed - entropy measures variance in agent behavior patterns, and debugging spirals have high behavioral variance. The spike correlates with the blocked outcome more than protocol composition.
**Updated**: questions.md

---

## 2026-01-09: Same protocol deviation, opposite outcome

**Expected**: Based on v32's success (-16.2% with synthesizer-as-planner, no dedicated planner), v34's identical protocol deviation should perform similarly or better.
**Observed**: v34 used exact same pattern (synthesizer-as-planner, 2 synthesizers, single_planner=false) but regressed +6.8%. Every task flow was worse: 001 +15%, 002 +6%, 003 +25%, 004 +31%.
**Gap**: Protocol patterns are not deterministic predictors of efficiency. v32 and v34 had identical protocol fidelity metrics (single_planner=false, single_synthesizer=false) but 23 percentage points of difference in outcome (-16.2% vs +6.8%). Either: (1) protocol composition is less important than other factors (prompt content, cache state, LLM sampling variance), or (2) the "synthesizer-as-planner" pattern has high variance outcomes. The mental model "protocol deviation = specific efficiency impact" is wrong.
**Updated**: questions.md (new question on protocol variance)

---

## 2026-01-09: Entropy spike refutes bimodal hypothesis

**Expected**: Based on v30=3.4, v31=4.4, v32=3.4, entropy appeared bimodal with two stable states. v33 should land at ~3.4 or ~4.4.
**Observed**: v33 achieved HT=4.7 - outside both hypothesized bands, and the highest entropy in recent runs.
**Gap**: Entropy is neither noise (too patterned) nor bimodal (v33 breaks the pattern) nor correlated with execution quality (v33 had clean execution with 0 fallbacks). Furthermore, v33 had BETTER protocol fidelity than v32 (single_planner=true, single_synthesizer=true) but HIGHER entropy. This inverts any assumption that "correct protocol = lower entropy." May need to investigate what the entropy metric actually measures at the component level.
**Updated**: questions.md (updated bimodal question)

---

## 2026-01-09: Protocol restoration yielded no efficiency gain

**Expected**: v32's protocol deviations (synthesizer-as-planner, 2 synthesizers, single_planner=false) should have been inefficient. Restoring proper protocol should improve tokens.
**Observed**: v33 restored proper protocol (single_planner=true, single_synthesizer=true) but achieved same token cost (628K vs 632K = -0.7%).
**Gap**: The "correct" protocol isn't necessarily the most efficient. v32's emergent pattern (synthesizer handling planning) was equally valid. Protocol fidelity metrics may be measuring conformance to expected patterns rather than actual efficiency. This suggests the protocol was over-specified - fewer constraints may allow agents to find efficient paths.
**Updated**: N/A

---

## 2026-01-09: ST dropped while tokens improved significantly

**Expected**: Higher ST (structural information) correlates with token efficiency. v31's ST=46.0 with 755K tokens should mean lower ST = higher tokens.
**Observed**: v32 achieved ST=42.8 (-7%) with 632K tokens (-16.2%). Inverse correlation.
**Gap**: ST may measure structural consistency/repeatability rather than absolute efficiency. A run can be less "structured" (in the epiplexity sense) while being more efficient. Agent composition affects ST: v32 had 9 agents vs v31's 10, and different agent type distribution (2 synthesizers, 3 builders vs 1 synthesizer, 4 builders). The metric may be sensitive to agent count, not just execution quality.
**Updated**: N/A (observation only, needs more data)

---

## 2026-01-09: Protocol deviations didn't cause regression

**Expected**: single_planner=false and single_synthesizer=false indicate protocol violations that typically cause inefficiency
**Observed**: v32's deviated protocol achieved -16.2% token reduction. The synthesizer handling planning duties and having two synthesizers actually worked better.
**Gap**: Protocol fidelity may be overfitted to a specific orchestration pattern. Alternative patterns (synthesizer-as-planner, multiple synthesizers) can be valid. The "correct" protocol isn't always the most efficient protocol.
**Updated**: N/A (needs investigation)

---

## 2026-01-08: Workspace warnings DO prevent runtime spirals

**Expected**: Based on v28 analysis, believed runtime interventions needed to be code-level (comments, test fixtures) - workspace warnings seemed insufficient since builders would already be deep in implementation by the time issues surfaced
**Observed**: v29 Builder 003 received workspace with "CRITICAL WARNING - date-string-mismatch" and completed in 154K tokens (vs v28's 286K = -46%). Reasoning trace shows builder applied the knowledge during implementation, not during debugging.
**Gap**: Underestimated workspace consumption timing. Builders read workspace at start, but also reference it DURING implementation. The warning was contextually available when writing date comparison code. Workspace warnings are a valid runtime intervention - they don't require code injection.
**Updated**: L011, questions.md

---

## 2026-01-08: Upfront knowledge doesn't prevent runtime spirals

**Expected**: Memory injection (prior_knowledge.md → session_context, planner prompts) would prevent date-string debugging spiral in v28
**Observed**: v28 Builder 003 hit 286K tokens with exact same pattern: "The database stores dates as strings" discovery during test verification
**Gap**: Knowledge seeding happens at task START. The date-string issue is discovered at test verification AFTER implementation. The builder has no opportunity to apply prior knowledge - it's in the middle of debugging when it discovers the issue. Cross-run learning needs runtime-level intervention (workspace warnings, code comments, test fixtures) not just upfront context.
**Updated**: Questions.md (new question about runtime vs planning knowledge)

---

## 2026-01-08: Incremental patches can regress

**Expected**: Each patch improves or is neutral; patches accumulate benefit
**Observed**: v22 added patches to v21, regressed +6.5%. More rules = worse performance.
**Gap**: Patches interact. Contradictory guidance causes agents to execute multiple paths.
**Updated**: L005, L008

---

## 2026-01-08: Ontological refactor magnitude

**Expected**: Refactor might improve 10-15% over patched version
**Observed**: v23 improved 35% over v22. Single decision point framing was transformative.
**Gap**: Underestimated cognitive load of accumulated rules. Clean ontology is not just cleaner - it's fundamentally more efficient.
**Updated**: L005

---

## 2026-01-08: First thought as efficiency predictor

**Expected**: Token cost determined by task complexity
**Observed**: First reasoning statement predicts cost regardless of task. "Clear picture" = cheap, "Let me understand" = expensive.
**Gap**: Cognitive state at start dominates task complexity. Context availability > task difficulty.
**Updated**: L006

---

## 2026-01-08: Planner errors cascade to builders

**Expected**: Builder debugging stays local to implementation
**Observed**: v21 builder 003 spent 313K tokens (6x normal) fixing test names - a planner verification coherence error.
**Gap**: Builders trust workspace completely. Upstream errors become downstream spirals.
**Updated**: L007

---

## 2026-01-08: Sequential routing enables learning

**Expected**: Task order doesn't matter much; parallel would be faster
**Observed**: v24 Task 003 (151K) benefited from Tasks 001-002 context. Same task in v23 (224K) without that context.
**Gap**: Knowledge propagation is a hidden dependency. Sequential routing is slower but smarter.
**Updated**: L009

---

## 2026-01-08: Memory seeded but not consumed

**Expected**: v26 < 650K tokens due to cross-run learning preventing date-string debugging spiral
**Observed**: v26 = 759K tokens (+6.6% from v24). Builder 003 hit exact same date-string issue (227K tokens vs v23's 224K).
**Gap**: Memory files existed in `.ftl/memory/` but no agent read them. Protocol changes (planner.md, router.md) were descriptive, not prescriptive. The actual `first_reads` pattern didn't change.
**Updated**: Fixed SKILL.md to inject prior_knowledge.md into session_context.md and planner prompts.

---

## 2026-01-06: Prohibition quantity irrelevant

**Expected**: More prohibitions → better compliance
**Observed**: 4 prohibitions achieved 0%; 1 structural reframe achieved 100%
**Gap**: Compliance is binary on framing, not gradual on quantity
**Updated**: L001

---
