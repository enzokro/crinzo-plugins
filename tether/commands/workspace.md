---
description: Query workspace state and lineage.
allowed-tools: Bash, Read, Glob, Grep
---

# Workspace Query

## Protocol

Parse $ARGUMENTS:

**No args** — overview:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/wql.py" stat
```

**"graph"** — tree view:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/wql.py" graph
```

**Number (e.g., "003")** — lineage:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/wql.py" lineage $SELECTOR
```

**"active" | "blocked" | "complete"** — filter:
```bash
ls -la workspace/*_${STATUS}*.md 2>/dev/null
```

**"roots"** — no parent:
```bash
ls workspace/*.md 2>/dev/null | while read f; do
  [[ ! "$f" =~ _from-[0-9] ]] && basename "$f"
done
```

**"tags"** — Key Findings:
```bash
grep -h "^#pattern/\|^#constraint/\|^#decision/" workspace/*_complete*.md 2>/dev/null | sort -u
```

**"find PATTERN"** — search:
```bash
grep -rn "PATTERN" workspace/*.md 2>/dev/null
```

## Indicators

- `[+]` complete
- `[~]` active
- `[!]` blocked
