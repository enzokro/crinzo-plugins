# Comparison: anki-v10 → anki-v12

*Generated: 2026-01-06 22:35*

---

## Token Observations

**Total tokens**: 4,807,247 → 3,940,886 (-866,361 (-18.0%))

**By category**:
  - input: 4,569 → 1,805 (-2,764 (-60.5%))
  - cache_read: 4,267,942 → 3,465,275 (-802,667 (-18.8%))
  - cache_create: 497,901 → 441,147 (-56,754 (-11.4%))
  - output: 36,835 → 32,659 (-4,176 (-11.3%))

**Cache efficiency**: 88.8% → 87.9%

---

## Agent Observations

**Agent count**: 19 → 14

**By type**:
  - planner: 1 → 1
    tokens: 77,170 → 67,696 (-9,474 (-12.3%))
  - router: 7 → 6
    tokens: 1,533,449 → 1,209,960 (-323,489 (-21.1%))
  - builder: 5 → 6
    tokens: 2,197,558 → 2,157,552 (-40,006 (-1.8%))
  - learner: 5 → 0 ✓
    tokens: 668,576 → 0 (-668,576 (-100.0%))
  - synthesizer: 1 → 1
    tokens: 330,494 → 505,678 (+175,184 (+53.0%))

---

## Protocol Observations

  - No learners in campaign: ✗ → ✓ (improved)
  - Single planner: ✓ → ✓
  - Single synthesizer: ✓ → ✓
  - Router/builder match: ✗ → ✓ (improved)
  - Router cache rate: 86% → 100% (changed)

---

## Questions This Raises

- Tokens increased by 53%. What drove this change?
- Learner count went from 5 to 0. What change caused this? Is it stable?
- Synthesizer tokens increased by 53%. Is output quality different?

---

*These are observations, not conclusions. Interpretation requires reflection.*