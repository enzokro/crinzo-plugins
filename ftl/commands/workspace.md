---
description: Query workspace state and lineage.
allowed-tools: Bash, Read, Glob, Grep
---

# Workspace Query

## Protocol

Parse $ARGUMENTS:

**No args** — overview:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/workspace.py" stat
```

**"graph"** — tree view:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/workspace.py" graph
```

**Number (e.g., "003")** — lineage:
```bash
source ~/.config/ftl/paths.sh 2>/dev/null; python3 "$FTL_LIB/workspace.py" lineage $SELECTOR
```

**"active" | "blocked" | "complete"** — filter:
```bash
ls -la .ftl/workspace/*_${STATUS}*.md 2>/dev/null
```

**"roots"** — no parent:
```bash
ls .ftl/workspace/*.md 2>/dev/null | while read f; do
  [[ ! "$f" =~ _from-[0-9] ]] && basename "$f"
done
```

**"tags"** — Key Findings:
```bash
grep -h "^#pattern/\|^#constraint/\|^#decision/" .ftl/workspace/*_complete*.md 2>/dev/null | sort -u
```

**"find PATTERN"** — search:
```bash
grep -rn "PATTERN" .ftl/workspace/*.md 2>/dev/null
```

## Indicators

- `[+]` complete
- `[~]` active
- `[!]` blocked
