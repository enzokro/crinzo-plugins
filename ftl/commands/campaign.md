---
name: campaign
description: Start or resume a development campaign.
allowed-tools: Bash, Read, Task, Glob
---

# Campaign

Start new or resume existing campaign.

## Protocol

Parse $ARGUMENTS:

**No args** — resume most recent:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/campaign.py" active
```

If campaign exists → invoke orchestrator to continue.
If no campaign → report "No active campaign. Provide objective to start."

**Objective provided** — start or match:

Check if matching campaign exists:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/campaign.py" active
```

If active campaign matches objective → resume.
If different campaign active → ask user:
```
Active campaign: existing-campaign

Options:
1. Complete existing first
2. Abandon existing, start new
3. Resume existing
```

If no active campaign → create via CLI (MANDATORY):

```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/campaign.py" campaign "$OBJECTIVE"
```

Verify campaign was created:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/campaign.py" active
```

Then invoke orchestrator:
```
Task tool with subagent_type: forge:forge-orchestrator
Prompt: "Resume campaign: $OBJECTIVE"
```

**NEVER write campaign JSON directly. The CLI is the only valid interface.**

## Output

**Starting new:**
```
Starting campaign: oauth-integration
Objective: Add OAuth with Google and GitHub

Invoking planner...
```

**Resuming:**
```
Resuming campaign: oauth-integration
Progress: 2/5 tasks complete

Next task: github-provider
```

**No campaign:**
```
No active campaign.

Usage: /forge <objective>
Example: /forge "Add OAuth support with Google and GitHub"
```
