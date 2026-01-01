---
description: Query workspace state and lineage.
allowed-tools: Bash, Read, Glob, Grep
---

# Workspace Query

## Protocol

Check workspace exists:
```bash
ls workspace/*.md 2>/dev/null || echo "No workspace"
```

Parse $ARGUMENTS:

**No args** — overview:
```bash
echo "complete: $(ls workspace/*_complete*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "active:   $(ls workspace/*_active*.md 2>/dev/null | wc -l | tr -d ' ')"
echo "blocked:  $(ls workspace/*_blocked*.md 2>/dev/null | wc -l | tr -d ' ')"
```

**"active" | "blocked" | "complete"** — filter:
```bash
ls -la workspace/*_${STATUS}*.md 2>/dev/null
```

**Number (e.g., "003")** — lineage:
```bash
python3 << 'EOF'
import re
from pathlib import Path

target = "$SELECTOR"
files = {}
for p in Path("workspace").glob("*.md"):
    m = re.match(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$', p.stem)
    if m:
        seq, slug, status, parent = m.groups()
        files[seq] = {"path": p.name, "parent": parent}

chain = []
current = target
while current and current in files:
    chain.append(current)
    current = files[current]["parent"]
chain.reverse()
print("Ancestors:", " → ".join(chain))
for seq in chain:
    print(f"  {files[seq]['path']}")
EOF
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
