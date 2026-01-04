---
name: status
description: Campaign and active workspace status.
allowed-tools: Bash, Read, Glob
---

# Status

Show campaign progress and workspace state.

## Protocol

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" status
```

## Output Format

**With active campaign:**
```
Campaign: oauth-integration (active)
Objective: Add OAuth with Google and GitHub
Started: 2025-01-02T10:30:00Z

Tasks: 3/5
  [+] 015_oauth-models (verified)
  [+] 016_google-provider (verified)
  [~] 017_github-provider (current)
      Verify: npm test src/auth/github
  [ ] 018_callback-handling
  [ ] 019_session-integration

Health: Tests 47/48 | Types OK | Lint 2 warnings

Precedent used:
  - #pattern/session-token-flow
  - #constraint/httponly-cookies

Patterns emerged:
  - #pattern/oauth-callback-flow

Precedent available for next task:
  - #pattern/callback-handling from [012]

Signals given: 1 positive

Active workspace files:
  [~] 017_github-provider_active.md

Campaigns: 1 active, 3 complete
```

**No active campaign:**
```
No active campaign.

Active workspace files:
  [~] 003_standalone-task_active.md

Campaigns: 0 active, 5 complete

Use /forge <objective> to start a campaign.
```

## Health Summary

Quick health check (timeout 10s):
```bash
# Detect project type and run appropriate check
npm test --silent 2>&1 | tail -3
npm run typecheck --silent 2>&1 | tail -1
npm run lint --silent 2>&1 | tail -1
```

Report summary line, not full output.

## Next Task Context

For next pending task, show:
- Verification strategy from campaign plan
- Available precedent from lattice query

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$LATTICE_LIB/context_graph.py" query "$NEXT_TASK_KEYWORDS"
```

## Details

Check for conflicts:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FORGE_LIB/forge.py" conflicts
```

If conflicts detected:
```
Warning: Active files not in current campaign:
  [~] 020_unrelated-task_active.md
```
