# Surprises

Gaps between prediction and reality. These reveal where mental models are wrong.

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
