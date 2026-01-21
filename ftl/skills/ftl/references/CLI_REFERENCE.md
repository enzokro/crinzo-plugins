# FTL CLI Reference

All paths use `${CLAUDE_PLUGIN_ROOT}` - this variable resolves to the plugin installation directory.
Arguments marked `POS` are positional (no flag). Arguments marked `FLAG` require the flag prefix.

**Storage Backend**: All data stored in SQLite database at `.ftl/ftl.db`. See DATABASE_SCHEMA.md for details.

**Stdin Pattern**: Commands reading JSON use heredoc. There is NO `--result` flag.
- CORRECT: `command <<< '{"key": "value"}'`
- WRONG: `command --result '{}'` ← flag does NOT exist

## exploration.py

| Command | Syntax | Notes |
|---------|--------|-------|
| write-result | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write-result --session ID --mode MODE` | stdin: explorer result JSON |
| session-status | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py session-status --session ID` | returns completion status |
| aggregate-session | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-session --session ID --objective "text"` | aggregates from DB |
| clear-session | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear-session --session ID` | removes session results |
| clear | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear` | clears exploration table |
| aggregate | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate --objective "text"` | stdin: JSON lines |
| write | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write` | stdin: exploration dict, writes to DB |
| read | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py read [--campaign-id ID]` | returns exploration from DB |
| get-structure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-structure` | |
| get-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-pattern` | |
| get-memory | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-memory` | |
| get-delta | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-delta` | |

## plan.py

| Command | Syntax | Notes |
|---------|--------|-------|
| write | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py write` | stdin: plan JSON, returns ID |
| read | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py read --id ID` | returns plan dict |
| get-active | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py get-active` | returns most recent active plan |
| mark-executed | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py mark-executed --id ID` | marks plan as executed |
| list | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/plan.py list [--status STATUS]` | list plans |

## campaign.py

| Command | Syntax | Notes |
|---------|--------|-------|
| create | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py create "objective" [--framework NAME]` | `objective` is POS |
| status | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py status` | |
| add-tasks | `cat plan.json \| python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py add-tasks` | reads stdin, validates DAG |
| update-task | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py update-task SEQ STATUS` | both POS |
| next-task | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py next-task` | returns first pending |
| ready-tasks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py ready-tasks` | returns all ready for parallel execution |
| cascade-status | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py cascade-status` | detects stuck campaigns |
| propagate-blocks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py propagate-blocks` | marks unreachable tasks blocked |
| complete | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py complete [--summary "text"]` | `--summary` is FLAG |
| active | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py active` | returns campaign or null |
| history | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py history` | |
| export | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py export OUTPUT [--start DATE] [--end DATE]` | `OUTPUT` is POS |
| fingerprint | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py fingerprint` | similarity fingerprint |
| find-similar | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py find-similar [--threshold F] [--max N]` | finds similar archived campaigns |
| get-replan-input | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py get-replan-input` | context for adaptive re-planning |
| merge-revised-plan | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/campaign.py merge-revised-plan PATH` | `PATH` is POS, merges revised plan |

## workspace.py

| Command | Syntax | Notes |
|---------|--------|-------|
| create | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan-id ID [--task SEQ]` | `--plan-id` REQUIRED (reads from plan table) |
| parse | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py parse PATH` | `PATH` is POS (path or workspace_id) |
| complete | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py complete PATH --delivered "text" [--utilized JSON]` | tracks helpful memories |
| block | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py block PATH --reason "text"` | `--reason` REQUIRED |
| list | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py list [--status STATUS]` | list all workspaces |
| get-injected | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py get-injected --workspace WS_ID` | returns injected memories [{name, type}] |
| clear-stale | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py clear-stale [--keep ID]` | clears workspaces from completed campaigns; keeps active campaign only by default |

## memory.py

| Command | Syntax | Notes |
|---------|--------|-------|
| context | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py context [--type TYPE] [--tags TAGS] [--objective TEXT] [--max-failures N] [--max-patterns N] [--all] [--include-tiers]` | `--objective` enables semantic retrieval, `--include-tiers` adds tier classification |
| add-failure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-failure --json '{...}'` | `--json` REQUIRED |
| add-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-pattern --json '{...}'` | `--json` REQUIRED |
| query | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py query "term"` | `term` is POS, semantic ranking |
| stats | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py stats` | counts, avg_importance, relationships |
| prune | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py prune [--max-failures N] [--max-patterns N] [--min-importance F] [--half-life D]` | removes low-importance entries |
| add-relationship | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-relationship SOURCE TARGET [--type failure\|pattern] [--rel-type TYPE]` | bidirectional graph edge |
| related | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py related NAME [--type failure\|pattern] [--max-hops N]` | weighted BFS traversal |
| feedback | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py feedback NAME --helped\|--failed [--type TYPE]` | records if memory was useful |
| feedback-batch | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py feedback-batch --utilized JSON --injected JSON` | batch feedback; also supports `--utilized-b64` `--injected-b64` for base64-encoded JSON |
| verify-loop | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py verify-loop` | diagnoses learning loop health |
| add-cross-relationship | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-cross-relationship FAILURE PATTERN [--type solves\|causes]` | links failure to solving pattern |
| get-solutions | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py get-solutions FAILURE` | patterns that solve a failure |

## observer.py

| Command | Syntax | Notes |
|---------|--------|-------|
| analyze | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py analyze [--workspace-dir PATH] [--no-verify]` | full extraction pipeline |
| verify-blocks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py verify-blocks [--workspace-dir PATH]` | verify all blocked workspaces |
| score | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py score PATH` | score single workspace |
| extract-failure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py extract-failure PATH` | extract failure from blocked workspace |
| list | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py list` | list workspaces by status |

## benchmark.py

| Command | Syntax | Notes |
|---------|--------|-------|
| run | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py run` | runs all benchmarks, stores in DB, returns JSON |
| report | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py report` | full benchmark report (from DB) |
| retrieval | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py retrieval` | retrieval speed benchmark |
| matching | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py matching` | semantic matching benchmark |
| learning | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py learning` | efficiency simulation |
| pruning | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py pruning` | pruning performance |
| get-run | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py get-run --run-id ID` | get run results from DB |
| compare | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py compare --run-a ID --run-b ID` | compare two runs |
| list-runs | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py list-runs` | list recent benchmark runs |

## orchestration.py

| Command | Syntax | Notes |
|---------|--------|-------|
| create-session | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py create-session` | returns session_id for explorer tracking |
| wait-explorers | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py wait-explorers --session ID [--required N] [--timeout S]` | blocks until quorum (polls explorer_result table) |
| check-explorers | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py check-explorers --session ID` | non-blocking status check |
| check-explorer-result | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py check-explorer-result --session ID --mode MODE` | checks if specific mode result exists (for EXPLORER_COMPLETION_PATTERN fallback) |
| validate-transition | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py validate-transition FROM TO` | both POS |
| emit-state | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/orchestration.py emit-state STATE [--meta JSON]` | `STATE` is POS, logs event |

## decision_parser.py

| Command | Syntax | Notes |
|---------|--------|-------|
| (default) | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/decision_parser.py INPUT_FILE [--validate]` | `INPUT_FILE` is POS, detects PROCEED/CLARIFY/CONFIRM |

Exit codes: 0=PROCEED, 1=UNKNOWN, 2=CLARIFY, 3=CONFIRM

## framework_registry.py

| Command | Syntax | Notes |
|---------|--------|-------|
| detect | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/framework_registry.py detect [PATH]` | `PATH` is optional POS (default: ".") |
| idioms | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/framework_registry.py idioms FRAMEWORK` | `FRAMEWORK` is POS, returns {required, forbidden} |
| weight | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/framework_registry.py weight FRAMEWORK` | `FRAMEWORK` is POS, returns complexity weight |
| list | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/framework_registry.py list` | returns JSON array of framework names |
