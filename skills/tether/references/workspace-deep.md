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
[Trace reasoning before implementing—every entry connects to Anchor]

## Close
Omitted: [things not implemented because not requested]
Delivered: [exact output]
Complete: [specific criteria met]
```

**Anchor**: The fixed point. Set once at file creation, never modified. Contains everything you're bound to—scope, exclusions, patterns, path, and delta.

**Trace**: Where you think. Write BEFORE implementing. Every entry traces back to the Anchor. Your scratchpad during work, your crystallized reasoning after.

**Close**: The proof. Filled in when work completes. What was delivered, what was omitted, how the Anchor was satisfied.

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

| System | Tracks | Lifecycle |
|--------|--------|-----------|
| TodoWrite | What you're doing | Items complete and disappear |
| Workspace | What you learned | Insights persist and compound |

Use both. They serve different purposes.

- Task list for execution tracking
- Workspace files for understanding accumulation

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
