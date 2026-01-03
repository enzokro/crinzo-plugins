# Forge

Meta-orchestrator for intelligent models collaborating with intelligent humans.

## Philosophy

**Production frameworks compensate for model limitations with orchestration overhead.**

**Forge amplifies human+agent collaboration with an intelligent model.**

```
Production: Model is component → orchestrate around limitations
Forge: Model is intelligence → structure for human leverage
```

Training wheels are for models that lose context, make frequent errors, and can't reason about complexity. Opus 4.5 on Claude Code doesn't need training wheels.

### The Five Commitments

#### 1. Verification-First

Every piece of work shaped by how to prove it correct.

Not: "Plan tasks, then figure out verification"
But: "How will we know this is right? Now shape the work."

#### 2. Scope-Bounded

Path/Delta makes human oversight meaningful.

When scope is visible and bounded, humans can reason about what the agent is doing, spot scope creep before it happens, and make informed decisions about escalation.

Unbounded agents aren't powerful. They're uncontrollable.

#### 3. Memory as Wisdom

Not retrieval. Wisdom.

- What worked? (signals)
- Why did we decide this? (rationale)
- What came before? (lineage)
- What should we try? (patterns with positive signal)

Query for insight, not similarity.

#### 4. Escalation as Success

When the reflector says ESCALATE, that's not failure.

That's the system correctly identifying where human judgment adds value.

The goal isn't "agent completes everything autonomously."
The goal is "human+agent together make better decisions than either alone."

#### 5. Campaign Coherence

The unit of work is:
```
Objective → Verification Strategy → Tasks → Learning
```

Not disconnected tool calls. Coherent campaigns with clear success criteria, bounded scope, accumulated wisdom, and human judgment where it matters.

## The Bet

Production frameworks bet on: "More orchestration → better outcomes"

Forge bets on: "Intelligent structure → human+agent leverage"

The goal isn't feature parity with LangGraph or CrewAI.
The goal is a different category: **intelligence-first orchestration**.

## Architecture

```
forge-orchestrator
    │
    ├─→ planner (verification-first decomposition)
    │
    ├─→ reflector (failure diagnosis, escalation)
    │
    ├─→ synthesizer (cross-campaign learning)
    │
    ├─→ scout (optional exploration)
    │
    └─→ tether (task execution with scope control)
            │
            └─→ lattice (semantic memory with signals)
```

## Commands

- `/forge:campaign` - Start or resume a campaign
- `/forge:status` - View campaign state
- `/forge:learn` - Surface learning from completed work
- `/forge:scout` - Explore codebase for context

## Version

6.0.0 - Intelligence-first orchestration
