# Task Granularity Heuristics

## Size Signals

| Signal | Task Size |
|--------|-----------|
| Single file modification | One task |
| Multiple files, same concern (e.g., "add field to model + migration + tests") | One task |
| Separate concerns (e.g., "add API endpoint" vs "add UI component") | Separate tasks |
| Verify command tests one behavior | One task |
| Implementation requires >150 lines | Consider splitting |

## Anti-Patterns (Bad Granularity)

- Task verify tests multiple unrelated behaviors → split
- Task touches >5 files → likely doing too much
- Task description uses "and" to connect unrelated work → split

## Good Signs

- Each task has a single, clear verify command
- Tasks can run in parallel when dependencies allow
- A task failure doesn't block unrelated work
