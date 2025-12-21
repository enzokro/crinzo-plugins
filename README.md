# Disciplined Creation

Claude Code plugin for scope-controlled development. Embeds checkpoints that prevent over-engineering and scope creep.

## Problem

AI assistants over-engineer. They add abstractions for flexibility nobody asked for, handle edge cases outside requirements, create new files when existing ones would work. This compounds across a session until the output diverges significantly from what was requested.

## Solution

Define scope boundaries before implementation. Use a workspace to externalize decisions. Check for drift during and after work.

## Workspace

Each task gets a file:

```
workspace/NNN_task-slug_status[_from-NNN].md
```

The file contains:
- **Anchor**: Exact behavior, what's excluded, patterns to follow
- **Transform**: Input → Processing → Output path
- **Patterns/Decisions/Constraints**: Written during work, before implementing
- **Verify**: What was delivered, what was deliberately omitted

Lineage suffix (`from-NNN`) tracks dependencies between tasks. `ls workspace/` queries all active work.

## Phases

1. **Triage**: Can this anchor to a single behavior? Does it need a workspace file or is execution obvious?
2. **Anchor**: Create workspace file. Define scope boundary.
3. **Transform**: Implement. Write reasoning to workspace before coding. Stop if scope expands.
4. **Verify**: Add omissions section. Rename file to final status.

## Drift Signals

These phrases indicate scope expansion. Halt and clarify:

- "flexible," "extensible," "comprehensive"
- "while we're at it," "might as well"
- "in case," "future-proof"

## Components

| Component | Purpose |
|-----------|---------|
| Skill | Auto-invoked on create/build/implement. Embeds checkpoint methodology. |
| code-builder agent | Test-first, edit-over-create, no unprompted abstractions. |
| `/dc:workspace` | Query active tasks and lineage. |
| `/dc:anchor [task]` | Create workspace file with scope boundary. |
| `/dc:verify [task]` | Complete task. Add omissions. Rename file. |
| `/dc:drift` | Review work against anchor for scope creep. |

## Constraints

| Constraint | Meaning |
|------------|---------|
| Edit over create | Modify existing before creating new |
| Concrete over abstract | Specific solution, not general framework |
| Present over future | Current requirements, not anticipated |
| Explicit over clever | Clarity over sophistication |

## Omissions

Every completion requires listing what was deliberately not implemented. "Nothing omitted" indicates either scope was too narrow or work exceeded scope. Adjacent work always exists. Name what you chose not to do.

## When to Use

- Precision matters more than speed
- Understanding should persist across sessions
- Reasoning needs to be visible
- Scope requires explicit negotiation

## When Not to Use

- Exploratory prototyping
- Autonomous long-running tasks (use Ralph or similar)
- Simple one-off queries

## Installation

```bash
claude /plugin install disciplined-creation@orch-v2
```

## Usage

```bash
/dc:workspace                              # check existing work
/dc:anchor implement password reset flow   # start new task
/dc:verify password-reset                  # complete task
```

## Structure

```
disciplined-creation/
├── skills/disciplined-creation/
│   ├── SKILL.md
│   └── references/
├── agents/code-builder.md
└── commands/
```

## License

MIT
