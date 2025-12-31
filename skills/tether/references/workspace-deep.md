# Cognitive Workspace

Context is the medium of thought—not a resource to conserve, but a workspace to cultivate.

The insight: Externalizing working memory frees mental bandwidth for higher-order reasoning. A thinker with pen and paper is more capable than one without—not because they document better, but because they think better.

---

## Why The Workspace Matters

The workspace folder is not documentation. It is not a log. It is **where you think**.

| Without Workspace | With Workspace |
|-------------------|----------------|
| Think, then maybe document | Think BY writing |
| Decisions made in your head | Decisions made on the page |
| Understanding vanishes after task | Understanding compounds across tasks |
| Each task starts fresh | Each task builds on what you know |
| Patterns rediscovered | Patterns propagate forward |

The workspace makes you more capable, not just more organized. Writing first, implementing second, forces articulation—and articulation clarifies thinking.

---

## The File As Living Document

Each workspace file has three sections:

```markdown
# NNN: Task Name

## Anchor
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]
Scope: [one sentence exact requirement]
Excluded: [what is not in scope]
Patterns: [existing patterns to follow]

## Trace
### T1: [Anchor fills—patterns found, approach, references Path]
### T2: [Build fills—after first step, references Anchor]
### T3: [Build fills—significant decision, references Anchor]

## Close
Delivered: [exact output matching Anchor scope]
Omitted: [what fell outside Path/Delta]
Complete: [specific criteria met]
```

Each section is produced by a phase and consumed by the next:

**Anchor** (Phase 2 output): The fixed point. Path, delta, scope, exclusions, patterns. Set once, never modified.

**Trace** (Phase 2-3 output): Decision traces with Anchor references.
- T1 filled at Anchor—patterns found, approach chosen, constraints identified
- T2, T3+ filled at Build—reasoning during implementation
- Each entry must reference Anchor explicitly (Path/Scope/Delta/Excluded)
- Pairing rule: every TodoWrite update pairs with a Trace write

**Close** (Phase 4 output): The proof. What was delivered, what was omitted, how the Anchor was satisfied.

---

## List of Lists (Simon)

Following Herbert Simon's *Sciences of the Artificial*: complex systems are nearly decomposable hierarchies. Information organizes as chunks containing chunks.

The workspace embodies this at two levels:

**Level 1: The folder** — each file is a chunk of understanding

**Level 2: Within files** — content nests hierarchically

```markdown
## Trace
- Authentication flow
  - Uses JWT tokens (not sessions)
  - Token refresh handled by interceptor
  - Auth state in AuthContext
- API patterns
  - REST endpoints at /api/v1/*
  - Error format: { error: string, code: number }
```

**Chunking principles**:

| Principle | Meaning |
|-----------|---------|
| Start flat | Nest only when complexity requires |
| Bound each level | ~5-7 items before creating sub-list |
| Name the chunk | Parent item describes the category |
| Depth limit 3 | Deeper means decompose differently |

Structure emerges organically. Don't force hierarchy; let it grow from content.

---

## Pruning

### Within Files

When understanding is superseded, replace don't append:

**Before**: "API uses REST" + "Actually, uses GraphQL"
**After**: "API uses GraphQL"

Supersession is not additive. Old understanding creates confusion.

### Across Files

When a workspace file is entirely superseded:
1. Create new file with updated understanding
2. Delete old file

Keep the workspace clean. `ls workspace/` should show the current truth.

---

## Retrieval

The naming convention enables filesystem queries:

| Need | Query |
|------|-------|
| What work exists? | `ls workspace/` |
| What's active? | `ls workspace/*_active*` |
| What's blocked? | `ls workspace/*_blocked*` |
| What came from 002? | `ls workspace/*from*002*` |
| Full context for 003 | `cat workspace/003_*.md` |

No special tooling. The filesystem is the query engine.

---

## TodoWrite Integration

**The Pairing Rule**: Every TodoWrite update pairs with a Trace write.

| System | Tracks | Lifecycle | Cadence |
|--------|--------|-----------|---------|
| TodoWrite | What you're doing | Items complete and disappear | Update per task |
| Trace | Why you're doing it | Persists and compounds | Every TodoWrite update |

- TodoWrite: execution items (what to do next)
- Trace: decision traces (why, referencing Anchor)

**Path Navigation**: Each Trace entry anchors your position:
- Which part of **Path** does this advance?
- Does this stay within **Delta**?
- What am I deliberately avoiding per **Excluded**?

---

## The Emergence

Simple elements + consistent constraints = complex capability.

- **Simple elements**: Files with structured names
- **Constraints**: Naming convention, status values, lineage suffixes
- **Emergence**: A queryable web of accumulated understanding

Each `ls workspace/` shows where you've been, where you are, and how pieces connect.

The workspace grows with you. Understanding compounds across sessions, across tasks, across time.

**One folder. One naming convention. Integrated into every phase.**

The filesystem becomes extended cognition.
