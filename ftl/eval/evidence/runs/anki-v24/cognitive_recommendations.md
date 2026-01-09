# Cognitive Analysis: anki-v23 → anki-v24

*Generated: 2026-01-08 21:35*

---

## Agent Comparison

| Step | Type | Task | A Pattern | B Pattern | Token Δ | Ratio Improved |
|------|------|------|-----------|-----------|---------|----------------|
| 0 | planner | - | `.` | `.` | -5% | No |
| 1 | router | 003 | `A.` | `..` | -5% | No |
| 2 | builder | 004 | `..A` | `AAA` | -27% | No |
| 3 | router | 001 | `A.` | `A.` | -3% | No |
| 4 | builder | 001 | `A..` | `...A` | +89% | No |
| 5 | router | 002 | `A.` | `..` | -2% | No |
| 6 | builder | 002 | `A..A` | `....A` | +70% | No |
| 7 | router | 004 | `EA` | `..` | -21% | No |
| 8 | builder | 003 | `AAA..A` | `E..A` | -55% | Yes |
| 9 | synthesizer | - | `E..` | `...` | -16% | No |

**Legend**: E=explore, A=action, .=neutral

---

## Recommendations

### builder.md → Execution

**Priority**: medium
**Change**: Add: "After reading workspace/context, Write or Edit immediately."
**Rationale**: first action at position 3
