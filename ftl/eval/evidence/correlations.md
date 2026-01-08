# Correlations

Patterns noticed across runs. Not automated detection—observations from reflection.

---

## Observed

### Cache efficiency ↔ token usage (negative correlation)

**Observation**: Higher cache efficiency tends to correlate with lower total token usage.

**Evidence**:
- v12: 87.9% cache efficiency, 3.94M tokens
- v10: 88.8% cache efficiency, 4.81M tokens (but learner overhead confounds)

**Confidence**: Low. Need more data points without confounding factors.

**Mechanism hypothesis**: Cache reads are cheaper than fresh context injection. More cache = fewer redundant calls.

---

### Protocol fidelity ↔ efficiency (unclear)

**Observation**: Perfect protocol fidelity (v12) coincided with better efficiency. But is this correlation or causation?

**Evidence**:
- v12: 100% fidelity, 14 agents, 3.94M tokens
- v10: 71.4% fidelity, 19 agents, 4.81M tokens

**Confound**: v10's poor fidelity *was* the learner spawning. The efficiency loss was directly caused by fidelity failure, not just correlated.

**Confidence**: Medium. The correlation is real but the mechanism is direct causation in this case.

---

## Hypothesized (untested)

### Cache hit rate ↔ decision quality

**Hypothesis**: Routers that hit cache make better routing decisions.

**Status**: Not yet measured. Need a way to evaluate "decision quality" beyond "it didn't fail."

---
