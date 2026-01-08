# Cognitive Analysis: anki-v13 → anki-v17

*Generated: 2026-01-08 10:46*

---

## Agent Comparison

| Step | Type | Task | A Pattern | B Pattern | Token Δ | Ratio Improved |
|------|------|------|-----------|-----------|---------|----------------|
| 0 | planner | - | `EEEA` | `.` | -76% | No |
| 1 | router | 001 | `AE.EA.` | `.EEEA.` | +4% | No |
| 2 | builder | 001 | `EEEA.E.....E...` | `A.A.A` | -88% | No |
| 3 | router | 002 | `.EEEA.` | `.EEEE..` | +38% | No |
| 4 | builder | 002 | `EEE.A.A.....A` | `E..E...A` | -79% | No |
| 5 | router | 003 | `EEEEA.` | `.EA.` | -29% | Yes |
| 6 | builder | 003 | `..A.....A` | `E.........A` | +58% | Yes |
| 7 | router | 004 | `.E.A.` | `.EE...` | +21% | No |
| 8 | builder | 004 | `..A` | `...A` | +2% | No |
| 9 | synthesizer | - | `.E.....` | `AEE.....` | +9% | Yes |

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
**Rationale**: explore:action ratio 2:1
