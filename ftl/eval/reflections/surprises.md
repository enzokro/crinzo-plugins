# Surprises

Gaps between prediction and reality. These reveal where mental models are wrong.

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
