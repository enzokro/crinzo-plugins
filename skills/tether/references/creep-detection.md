# Scope Creep Detection

Creep occurs in exactly two ways: deviating from the Path or exceeding the Delta. Everything else is a symptom of these two.

---

## The Two Patterns

### 1. Path Deviation

You've moved off the defined transformation journey.

**Signals**:
- Changes to files not on the Path
- Adding transformations not specified
- Handling edge cases outside Path scope

**Question**: Is this step on the Anchor's Path?

**If no**: You've deviated. Return to the Path or acknowledge the deviation in Trace.

### 2. Delta Exceeded

You've done more than the minimal change requires.

**Signals**:
- Abstractions not required by the change
- Error handling beyond what the change needs
- "While I'm here..." additions
- Future-proofing hooks

**Question**: Does this exceed the smallest change achieving the requirement?

**If yes**: You've exceeded Delta. Remove the excess or justify why Delta needs expansion.

---

## Quick Reference

| Type | Signal | Question | Response |
|------|--------|----------|----------|
| Path deviation | Off-Path changes | On the Anchor's Path? | Return to Path |
| Delta exceeded | More than minimal | Smallest change? | Remove excess |

---

## Integration with Build Phase

During Build, periodically ask:

- Am I still on the Path?
- Am I within Delta?

If uncertain: run `/tether:creep`, reflect, correct course.

---

## The Trace Connection

Traces anchor your position on the Path. When you articulate what you're doing against the Anchor, drift becomes visible.

**The Pairing Rule**: Every TodoWrite update pairs with a Trace write. Ride it. When you update TodoWrite, also write to a Trace checkpoint.

Trace first. Path and Delta awareness surfaces when you try to articulate what you're doing.
