# Scope Creep Detection

Creep occurs when implementation expands beyond the Anchor. This reference provides detection patterns—not enforcement rules. Internalized discipline replaces external enforcement.

---

## The Five Patterns

### 1. Over-Engineering

**Signals**: Interfaces for single implementations, generic parameters for specific functions, plugin architectures for monolithic needs, factory patterns for direct construction.

**Question**: Was this abstraction in the Anchor, required by a test, or present elsewhere in the codebase?

**Three "no"s**: Remove. Implement the concrete solution.

### 2. Scope Expansion

**Signals**: Adding logging when not requested, error handling beyond requirements, utility functions for single use, configuration for fixed values.

**Question**: Was this capability specified in the Anchor?

**If no**: Remove. Creep compounds; small additions accumulate.

### 3. Verbosity

**Signals**: Comments explaining obvious code, multiple examples for clear concepts, extensive documentation for simple functions, TODO markers.

**Question**: Does this add information not already evident from the code itself?

**If no**: Remove. Code should be self-documenting.

### 4. Pattern Violation

**Signals**: New file structures diverging from existing, different naming conventions, alternative import patterns, non-standard directory placement.

**Question**: Does this match the patterns in the Anchor or established in the codebase?

**If no**: Halt. Align before continuing.

### 5. Future-Proofing

**Signals**: "In case we need..." additions, extensibility hooks unused, configuration for single values, optional parameters without current use.

**Question**: Does the Anchor require this, or is it anticipating future needs?

**If anticipating**: Remove. YAGNI—You Aren't Gonna Need It.

---

## Quick Reference

| Pattern | Signal | Question | Response |
|---------|--------|----------|----------|
| Over-engineering | Abstractions not in Anchor | In Anchor/tested/existing? | Remove if no |
| Scope expansion | "And also" additions | In Anchor? | Remove if no |
| Verbosity | Excessive explanation | Adds non-obvious info? | Remove if no |
| Pattern violation | New architecture | Matches existing? | Halt, align |
| Future-proofing | Options not needed | In Anchor? | Remove if anticipating |

---

## Integration with Build Phase

During Build, periodically ask:

- Am I adding lines that don't map to the Anchor?
- Am I creating abstractions without test coverage?
- Am I handling errors without specified failure modes?
- Am I creating files when editing would suffice?
- Is my Trace section empty? (Silent creep)

If yes to any: run `/tether:creep`, name what crept in, remove it, continue simpler.

---

## The Trace Connection

An empty Trace section during active work is itself a creep signal. It means implementation is happening without externalized reasoning—the conditions under which creep thrives.

Trace first. Creep surfaces when you try to articulate what you're doing against the Anchor.
