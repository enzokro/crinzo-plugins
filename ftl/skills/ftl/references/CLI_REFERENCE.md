# FTL CLI Reference

All paths use `${CLAUDE_PLUGIN_ROOT}` - this variable resolves to the plugin installation directory.
Arguments marked `POS` are positional (no flag). Arguments marked `FLAG` require the flag prefix.

## exploration.py

| Command | Syntax | Notes |
|---------|--------|-------|
| clear | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py clear` | removes exploration.json |
| aggregate | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate --objective "text"` | stdin: JSON lines |
| aggregate-files | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py aggregate-files --objective "text"` | reads .ftl/cache/explorer_*.json |
| write | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py write` | stdin: exploration dict |
| read | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py read` | returns exploration.json |
| get-structure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-structure` | |
| get-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-pattern` | |
| get-memory | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-memory` | |
| get-delta | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/exploration.py get-delta` | |

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
| create | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py create --plan PATH [--task SEQ]` | `--plan` REQUIRED |
| parse | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py parse PATH` | `PATH` is POS |
| complete | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py complete PATH --delivered "text" [--utilized JSON]` | tracks helpful memories |
| block | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/workspace.py block PATH --reason "text"` | `--reason` REQUIRED |

## memory.py

| Command | Syntax | Notes |
|---------|--------|-------|
| context | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py context [--type TYPE] [--tags TAGS] [--objective TEXT] [--max-failures N] [--max-patterns N] [--all] [--include-tiers]` | `--objective` enables semantic retrieval, `--include-tiers` adds tier classification |
| add-failure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-failure --json '{...}'` | `--json` REQUIRED |
| add-pattern | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-pattern --json '{...}'` | `--json` REQUIRED |
| query | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py query "term"` | `term` is POS, semantic ranking |
| stats | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py stats` | counts, avg_importance, relationships |
| prune | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py prune [--max-failures N] [--max-patterns N] [--min-importance F] [--half-life D]` | removes low-importance entries |
| add-relationship | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-relationship SOURCE TARGET [--type failure\|pattern]` | bidirectional graph edge |
| related | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py related NAME [--type failure\|pattern] [--max-hops N]` | weighted BFS traversal |
| feedback | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py feedback NAME --helped\|--failed [--type TYPE]` | records if memory was useful |
| add-cross-relationship | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py add-cross-relationship FAILURE PATTERN [--type solves\|causes]` | links failure to solving pattern |
| get-solutions | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/memory.py get-solutions FAILURE` | patterns that solve a failure |

## observer.py

| Command | Syntax | Notes |
|---------|--------|-------|
| analyze | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py analyze [--workspace-dir PATH] [--no-verify]` | full extraction pipeline |
| verify-blocks | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py verify-blocks [--workspace-dir PATH]` | verify all blocked workspaces |
| score | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py score PATH` | score single workspace |
| extract-failure | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/observer.py extract-failure PATH` | extract failure from blocked workspace |

## benchmark.py

| Command | Syntax | Notes |
|---------|--------|-------|
| report | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py report` | full benchmark report |
| run | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py run` | JSON results |
| learning | `python3 ${CLAUDE_PLUGIN_ROOT}/lib/benchmark.py learning` | efficiency simulation |
