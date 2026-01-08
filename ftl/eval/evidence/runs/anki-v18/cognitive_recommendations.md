# Cognitive Analysis: anki-v17 → anki-v18

*Generated: 2026-01-08 11:40*

---

## Agent Comparison

| Step | Type | Task | A Pattern | B Pattern | Token Δ | Ratio Improved |
|------|------|------|-----------|-----------|---------|----------------|
| 0 | planner | - | `.` | `.` | -3% | No |
| 1 | router | 001 | `.EEEA.` | `.EEEA.` | +11% | No |
| 2 | builder | 001 | `A.A.A` | `EA.A.` | -8% | Yes |
| 3 | router | 002 | `.EEEE..` | `.EE..` | -19% | No |
| 4 | builder | 002 | `E..E...A` | `AA.A` | -36% | No |
| 5 | router | 003 | `.EA.` | `EE.E..` | +72% | No |
| 6 | builder | 003 | `E.........A` | `EA..A` | -55% | Yes |
| 7 | router | 004 | `.EE...` | `EEEA.` | -0% | Yes |
| 8 | builder | 004 | `...A` | `..A` | -16% | No |
| 9 | synthesizer | - | `AEE.....` | `.....` | -21% | No |

**Legend**: E=explore, A=action, .=neutral

---

## Recommendations

### router.md → Core Discipline

**Priority**: high
**Change**: Add: "Act within first 3 tool calls. Do not explore to understand; understand to act."
**Rationale**: explore:action ratio 3:1

### router.md → Execution

**Priority**: medium
**Change**: Add: "After reading workspace/context, Write or Edit immediately."
**Rationale**: first action at position 4

### router.md → Constraints

**Priority**: medium
**Change**: Add: "Maximum 2 consecutive Reads before Write/Edit."
**Rationale**: explore burst of 3 consecutive traces
