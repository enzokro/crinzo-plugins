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
Scope: [one sentence exact requirement]
Excluded: [what is not in scope]
Patterns: [existing patterns to follow]
Path: [Input] → [Processing] → [Output]
Delta: [smallest change achieving requirement]

## Trace
### T1: [filled at Anchor—initial understanding, patterns found, approach]
### T2: [filled at Build—after first implementation step]
### T3: [filled at Build—before closing]

## Close
Omitted: [things not implemented because not requested—MUST be non-empty]
Delivered: [exact output matching Anchor scope]
Complete: [specific criteria met]
```

Each section is produced by a phase and consumed by the next:

**Anchor** (Phase 2 output): The fixed point. Scope, exclusions, patterns, path, delta. Set once, never modified.

**Trace** (Phase 2-3 output): Decision traces as numbered checkpoints.
- T1 filled at Anchor phase—initial understanding before implementation
- T2, T3+ filled at Build phase—reasoning during implementation
- Every TodoWrite update pairs with a Trace write
- Empty checkpoints = missing decision trace

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

**The Pairing Rule**: Every TodoWrite update pairs with a Trace write. They move together.

| System | Tracks | Lifecycle | Phase |
|--------|--------|-----------|-------|
| TodoWrite | What you're doing | Items complete and disappear | Build |
| Trace | What you're thinking | Checkpoints persist and compound | Anchor + Build |

- TodoWrite: execution items (what to do next)
- Trace: decision traces (T1 at Anchor, T2+ at Build)

**The structural guarantee**: You will update TodoWrite—that's your locked-in pattern. The pairing rule rides that pattern. When you update TodoWrite, also write to Trace.

**Contract enforcement**:
- T1 must be filled before Build phase starts (Anchor's output)
- T2, T3 must be filled before Close phase starts (Build's output)
- Empty checkpoints block the next phase

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
