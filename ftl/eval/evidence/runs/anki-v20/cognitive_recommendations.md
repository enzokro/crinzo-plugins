# Cognitive Analysis: anki-v19 → anki-v20

*Generated: 2026-01-08 20:19*

---

## Agent Comparison

| Step | Type | Task | A Pattern | B Pattern | Token Δ | Ratio Improved |
|------|------|------|-----------|-----------|---------|----------------|
| 0 | planner | - | `..` | `.` | -47% | No |
| 1 | router | 001 | `..` | `...` | -56% | No |
| 2 | builder | 001 | `..AA` | `.AA` | -22% | No |
| 3 | router | 002 | `.A.` | `...` | -16% | No |
| 4 | builder | 002 | `A..A` | `.A..A` | +14% | No |
| 5 | router | 003 | `.EA.` | `A.` | -57% | No |
| 6 | builder | 003 | `.AE.AA` | `E..E...A` | +60% | No |
| 7 | router | 004 | `.EA.` | `..` | -41% | No |
| 8 | builder | 004 | `EAA.A` | `E.A` | -41% | No |
| 9 | synthesizer | - | `.A..` | `E...` | -3% | No |

**Legend**: E=explore, A=action, .=neutral

---

## Recommendations

### builder.md → Core Discipline

**Priority**: high
**Change**: Add: "Act within first 3 tool calls. Do not explore to understand; understand to act."
**Rationale**: explore:action ratio 2:1

### builder.md → Execution

**Priority**: medium
**Change**: Add: "After reading workspace/context, Write or Edit immediately."
**Rationale**: first action at position 7

### synthesizer.md → Core Discipline

**Priority**: high
**Change**: Add: "Act within first 3 tool calls. Do not explore to understand; understand to act."
**Rationale**: explore:action ratio 1:0
