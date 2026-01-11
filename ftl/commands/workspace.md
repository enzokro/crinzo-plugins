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
ls -la .ftl/workspace/*_${STATUS}*.xml 2>/dev/null
```

**"roots"** — no parent:
```bash
ls .ftl/workspace/*.xml 2>/dev/null | while read f; do
  [[ ! "$f" =~ _from-[0-9] ]] && basename "$f"
done
```

**"tags"** — Key Findings (extract from XML):
```bash
python3 -c "
import xml.etree.ElementTree as ET
from pathlib import Path
patterns = set()
for ws in Path('.ftl/workspace').glob('*_complete.xml'):
    tree = ET.parse(ws)
    for p in tree.findall('.//pattern'):
        name = p.get('name')
        if name: patterns.add(f'#pattern/{name}')
    for f in tree.findall('.//failure'):
        name = f.get('name')
        if name: patterns.add(f'#failure/{name}')
for p in sorted(patterns):
    print(p)
"
```

**"find PATTERN"** — search:
```bash
grep -rn "PATTERN" .ftl/workspace/*.xml 2>/dev/null
```

## Indicators

- `[+]` complete
- `[~]` active
- `[!]` blocked
