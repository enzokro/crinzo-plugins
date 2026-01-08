# FTL Evaluation Chronicle

Learnings compound into FTL's decision memory via `./eval.sh integrate`.

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
