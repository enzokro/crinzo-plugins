# FTL Assessment: From Defensive Scaffolding to Collaborative Amplification

## The North Star

> **Augmentation, not replacement.**

FTL exists to make developers *more capable*, not to replace them. The vision isn't an autonomous orchestrator that runs forever. It's a **human-steered, scoped, evolving system** where:
- The human provides direction and judgment
- The AI provides capability and execution
- Knowledge compounds across sessions
- Each task accomplishes more than predecessors dreamed possible

This is the **gestalt** vision: human + AI > human alone > AI alone.

## Two Competing Paradigms

| Aspect | Autonomy Paradigm | Gestalt Paradigm |
|--------|-------------------|------------------|
| **Goal** | AI orchestrates itself | Human-AI collaboration |
| **Control** | Session decides transitions | Human steers, AI amplifies |
| **Scope** | Run until done | Bounded, reviewable work |
| **Trust model** | Trust the AI completely | Trust through transparency |
| **North star** | Autonomous agents | Augmented developers |

OpenProse represents the autonomy paradigm: "The session is the IoC container."

FTL represents the gestalt paradigm: **The developer is the orchestrator; the AI is the amplifier.**

The question isn't "Does FTL let the AI orchestrate itself?" but "Does FTL enable developers to accomplish more?"

---

## Part I: The Original Triplet (What We Started With)

### Quantitative Baseline

| Plugin | Agents | Commands | Lib Files | State System |
|--------|--------|----------|-----------|--------------|
| **forge-v1** | 5 | 4 | 1 (23KB) | campaigns/*.json |
| **tether-v1** | 5 | 4 | 1 (3.8KB) | workspace/*.md |
| **lattice-v1** | 2 | 7 | 4 (27KB) | .lattice/*.json (3 files) |
| **TOTAL** | **12** | **15** | **6** | **3 separate systems** |

### Architectural Awkwardness

#### 1. Orchestrator Nesting Violations

The triplet was designed with hierarchical composition:
```
forge-orchestrator → tether-orchestrator → phases
```

**Problem**: Claude's Task tool forbids subagent→subagent spawning. This architectural assumption was fundamentally incompatible with the runtime.

**Solution discovered**: Flatten to main thread spawning phases directly. But this left `tether-orchestrator.md` as documentation of a pattern that *doesn't work*.

**Cognitive overhead**: Developers reading the code see an orchestrator that exists but isn't called. Confusion between design intent and runtime reality.

#### 2. State Fragmentation

Three plugins, three mental models, three state backends:

| What | Where | Who Owns |
|------|-------|----------|
| Campaign status | forge: campaigns/*.json | forge.py |
| Task work | tether: workspace/*.md | anchor/builder |
| Decision patterns | lattice: .lattice/*.json | context_graph.py |

**Context loss**: A task completion requires querying all three systems. FORGE doesn't directly invoke LATTICE—the protocol says "at campaign close" but implementation is implicit.

**Example of fragmentation** (forge-orchestrator.md line 188):
```bash
python3 "$LATTICE_LIB/context_graph.py" mine
```
FORGE calls LATTICE's CLI directly instead of the agent. Abstraction layers blur.

#### 3. Workspace as Implicit Contract

The workspace file format is the actual interface between plugins, but it's defined in three places:
- `anchor.md` (creation spec)
- `code-builder.md` (update spec)
- `miner.md` (parsing spec)

Three separate understandings of the same structure. No canonical source of truth.

#### 4. Concept Drift

LATTICE's `concepts.py` contains 54 hand-curated concept clusters:
```python
"auth": ["authentication", "session", "login", "credential", "token", ...]
```

**Problem**: Static at plugin creation. Real patterns emerge at runtime. Two parallel search paths (concept-based vs embedding-based) with unclear precedence.

#### 5. Verification Strategy Loss

PLANNER discovers verification commands. This becomes part of workspace anchor. But verification *outcomes* are only in traces—LATTICE doesn't track "which verification strategies worked historically?"

Verification knowledge accumulates but isn't mined for patterns.

### The Triplet's Fundamental Tension

The triplet was **defensive scaffolding**—designed to constrain models that drifted. It assumed:
- Models need external structure to stay on task
- Agents should be small to prevent scope creep
- Separation enforces discipline

This created an *external orchestration* pattern: the plugin structure coordinates agents from outside their cognition.

---

## Part II: The Golden Synthesis (What We Built)

### Quantitative Result

| Metric | Triplet | FTL | Change |
|--------|---------|-----|--------|
| Agents | 12 | 6 | -50% |
| Commands | 15 | 9 | -40% |
| Memory files | 3 | 1 | unified |
| State systems | 3 | 1 | unified |
| Lib LOC | ~2500 | ~2200 | consolidated |

### The Six Irreducible Agents

| Agent | Role | Why Irreducible |
|-------|------|-----------------|
| **Router** | Route + explore + anchor | Single pass avoids context loss |
| **Builder** | TDD implementation | Needs focused implementation context |
| **Reflector** | Failure diagnosis | Fresh perspective on failures is valuable |
| **Learner** | Extract + index patterns | Sequential on same files |
| **Planner** | Campaign decomposition | Verification-first reasoning |
| **Synthesizer** | Meta-pattern extraction | Cross-campaign correlation |

### Key Consolidations

#### assess + anchor → router
**Problem solved**: Assess decided "full" without exploring; anchor rebuilt understanding.
**Principle applied**: Merge where context loss hurts.

#### reflect + miner → learner
**Problem solved**: Both read same workspace files sequentially.
**Principle applied**: Merge when cognitive task is same, just split artificially.

#### surface, scout → inlined
**Problem solved**: Pure query wrappers with no reasoning.
**Principle applied**: Inline where it's just retrieval.

#### reflector → kept separate
**Problem solved**: None—this is *correct* separation.
**Principle applied**: Separate where cognitive focus helps. Fresh perspective on failures has genuine value.

### Memory Unification (Phase B)

```
BEFORE: index.json + edges.json + signals.json
AFTER:  memory.json (v2, with auto-migration)
```

Single source of truth. Signals merged into patterns. Edges cached but computed during mine. Backward-compatible migration.

### Command Consolidation (Phase C)

```
BEFORE: 16 commands (many redundant with ftl.md routing)
AFTER:  9 commands (unique capabilities only)
```

`/ftl campaign`, `/ftl query`, `/ftl status` collapsed into ftl.md routing. Deleted: campaign.md, status.md, query.md, mine.md, stats.md, scout.md, anchor.md.

### Decision-Centric Workspace (Phase D)

```
BEFORE: Task-centric (Anchor section with Path/Delta)
AFTER:  Decision-centric (Question/Precedent/Options/Decision/Implementation)
```

**Bidirectional knowledge flow**:
- Memory → Workspace: Router injects precedent before builder starts
- Workspace → Memory: Richer decision structure (question, options, choice)

---

## Part III: Honest Assessment Through the Gestalt Lens

### Where FTL Succeeds as Collaborative Amplification

#### 1. Bounded, Reviewable Work

Every task produces a workspace file the human can inspect:
- **Question** frames what decision was made
- **Options Considered** shows alternatives explored
- **Decision** documents the choice with rationale
- **Implementation** (Path/Delta) scopes the change
- **Key Findings** extracts transferable knowledge

**Gestalt success**: The human can review, learn from, and course-correct AI work. Transparency enables trust.

#### 2. Human-Steered Cognitive Flow

The main thread dispatches agents:
```
/ftl <task> → router → builder → learner
```

**This is a feature, not a bug.** The human invokes `/ftl`. The human reviews workspace files. The human signals pattern success/failure. The human decides when to start campaigns.

**Gestalt success**: Human remains in the loop at every macro decision point.

#### 3. Knowledge Compounding Under Human Guidance

The signal system (+/-) requires human judgment:
```
/ftl:signal + #pattern/session-rotation
/ftl:signal - #antipattern/jwt-localstorage
```

Patterns don't automatically get positive signals from "passing tests." The *human* marks what worked. The *human* marks what failed. This is augmented judgment, not autonomous evaluation.

**Gestalt success**: Memory evolves through human curation, not AI self-assessment.

#### 4. Precedent Injection with Human Override

Router injects precedent from memory:
```
## Precedent
Related: [015] auth-refactor
Patterns: #pattern/session-token-flow (+2)
Antipatterns: #antipattern/jwt-localstorage (-2)
```

But the human can override. The workspace file is editable. Bad precedent can be removed. Missing context can be added.

**Gestalt success**: AI surfaces relevant history; human decides what's relevant.

#### 5. Scoped Execution (Path + Delta)

Every task has explicit boundaries:
- **Path**: What transformation occurs
- **Delta**: Which files can be touched
- **Verify**: How to prove success

The Delta hook prevents scope creep—the AI can't modify files outside the declared scope.

**Gestalt success**: Human sets boundaries; AI works within them.

### Where FTL Falls Short for Gestalt Collaboration

#### 1. Cognitive Overhead for Simple Tasks

The full workspace format (Question/Precedent/Options/Decision/Implementation) is heavyweight for "fix this typo."

**Current mitigation**: Router can return `direct` for simple tasks, skipping workspace creation.

**Gap**: The direct/full threshold is router's judgment, not human's explicit choice. Human should be able to say "this is simple, just do it."

#### 2. Campaign Opacity

Campaigns decompose objectives into tasks, but the decomposition happens in planner—not visible to the human until it's done.

**Gap**: Human should see the plan before execution starts. Current flow: plan → execute. Better flow: plan → human reviews → execute.

#### 3. Pattern Extraction Requires Discipline

Learner extracts patterns to Key Findings, but only if the human (or AI) recognizes something is extractable.

**Gap**: Easy to complete tasks without extracting knowledge. The system doesn't prompt "Was there anything reusable here?"

#### 4. Query Friction

To retrieve precedent manually, human must:
```bash
python3 "$FTL_LIB/context_graph.py" query "auth"
```

**Gap**: Should be `/ftl query auth` or even inline in natural language. Memory should be conversationally accessible.

#### 5. No Explicit Human Checkpoints

The router→builder→learner flow runs without pause. Human only intervenes on failure (reflector) or after completion.

**Gap**: For high-stakes tasks, human might want checkpoint: "Router found these files in scope—proceed?" Current: all-or-nothing.

### The Fundamental Question (Revised)

**Autonomy paradigm asks**: Can the AI orchestrate itself?
**Gestalt paradigm asks**: Can the human accomplish more with the AI?

FTL succeeds at:
- Transparent, reviewable work (workspace files)
- Human-curated knowledge (signal system)
- Bounded execution (Path/Delta/Verify)
- Scoped phases (router/builder/learner)

FTL needs improvement for:
- Lightweight mode for simple tasks
- Plan visibility before execution
- Prompting for knowledge extraction
- Conversational memory access
- Optional human checkpoints

---

## Part IV: The Next Evolution (Gestalt-Aligned)

### What Opus 4.5 Enables

The triplet was built for earlier models that drifted. Opus 4.5 changes the equation:

| Capability | Impact on FTL |
|------------|---------------|
| **Extended thinking** | Can hold complex context without losing thread |
| **Instruction following** | Respects Path/Delta/Verify without constant enforcement |
| **Self-correction** | Catches own errors, reducing reflector invocations |
| **Nuanced judgment** | Router decisions are more reliable |

**The implication**: FTL can trust Opus 4.5 more than its predecessors. But "trust" means "collaborate," not "abdicate."

### The Gestalt Evolution Path

Rather than autonomous orchestration, the next evolution should deepen human-AI collaboration:

#### 1. Explicit Control Levels

Let humans choose their involvement:
```
/ftl fix typo              → direct (minimal)
/ftl add auth              → full (standard)
/ftl! add auth             → checkpoint (high-stakes)
```

- **Direct**: AI executes immediately, no workspace
- **Full**: AI creates workspace, executes, extracts knowledge
- **Checkpoint**: AI proposes scope, human approves before execution

#### 2. Plan-Before-Execute for Campaigns

```
/ftl campaign add OAuth
```

Current: Planner decomposes → executes all tasks
Better: Planner decomposes → **shows plan** → human approves/modifies → executes

The human should see the battle plan before the battle.

#### 3. Conversational Memory

```
Human: "What patterns have worked for auth?"
AI: [queries memory, surfaces precedent conversationally]
Human: "The session-rotation pattern—when did we use that?"
AI: [traces pattern to decisions]
```

Memory should be a conversation partner, not just CLI queries.

#### 4. Prompted Knowledge Extraction

After task completion:
```
AI: "Task complete. I noticed a potential pattern: using httpOnly cookies
     with CSRF tokens. Should I extract this to Key Findings?"
Human: "Yes, tag it #pattern/secure-cookie-auth"
```

The AI prompts; the human curates.

#### 5. Adaptive Workspace Format

Simple tasks → lightweight format:
```markdown
# 042: Fix typo in README
Delta: README.md
Delivered: Fixed "teh" → "the" on line 15
```

Complex tasks → full format:
```markdown
# 043: Session Persistence Strategy
## Question ...
## Precedent ...
## Options Considered ...
[full decision-centric format]
```

Router decides based on task complexity, but human can override.

### The Gestalt Flywheel

```
Human provides direction
        ↓
AI executes with Opus 4.5 capability
        ↓
Workspace materializes reasoning (transparent)
        ↓
Human reviews, signals patterns (+/-)
        ↓
Memory compounds (curated knowledge)
        ↓
Future tasks benefit (precedent injection)
        ↓
Human accomplishes more (gestalt amplification)
        ↓
[cycle repeats with richer context]
```

Each cycle, the human-AI gestalt becomes more capable. Not because the AI is autonomous, but because the collaboration has compounding returns.

---

## Summary: The Assessment

### What Changed (Triplet → FTL)

| Before | After |
|--------|-------|
| 3 plugins, 12 agents, 15 commands | 1 plugin, 6 agents, 9 commands |
| 3 state systems | 1 unified memory |
| Task-centric workspace | Decision-centric workspace |
| One-way knowledge flow | Bidirectional (precedent injection) |
| Orchestrator nesting violations | Flat main-thread spawning |
| Implicit contracts | Explicit workspace format |
| Defensive scaffolding | Collaborative amplification |

### Where FTL Succeeds (Gestalt Lens)

1. **Transparency**: Workspace files make AI reasoning visible
2. **Human curation**: Signal system requires human judgment
3. **Bounded execution**: Path/Delta/Verify prevent scope creep
4. **Knowledge compounding**: Precedent injection helps future tasks
5. **Opus 4.5 leverage**: Reduced agents work because model is capable

### Where FTL Can Improve (Gestalt Lens)

1. **Control granularity**: direct/full/checkpoint modes
2. **Campaign visibility**: Plan-before-execute
3. **Knowledge prompting**: AI asks "should I extract this?"
4. **Conversational memory**: Query as dialogue
5. **Adaptive format**: Lightweight for simple, full for complex

### The Verdict

FTL embodies: **"Augmentation, not replacement."**

The triplet was defensive scaffolding—constraining models that drifted.
FTL is collaborative amplification—enabling humans to accomplish more.

The next evolution isn't autonomous orchestration. It's **deeper collaboration**:
- More explicit control levels
- More visibility into AI planning
- More conversational knowledge access
- More prompted knowledge extraction

**FTL is not a bridge to AI autonomy. It's a foundation for human-AI gestalt.**

The destination isn't the AI orchestrating itself. It's the human accomplishing things that were previously impossible—because Opus 4.5 is a true collaborator, not just a tool.
