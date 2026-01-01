---
description: Query the cognitive workspace. Shows active tasks, lineage, and available context.
allowed-tools: Bash, Read, Glob, Grep
---

# Workspace Query

Query the cognitive workspace for this project.

## Protocol

1. Check if workspace exists:
   ```bash
   ls workspace/*.md 2>/dev/null || echo "No workspace folder found"
   ```

2. Parse $ARGUMENTS for query type:

   **No arguments (default)** — show overview:
   ```bash
   echo "=== WORKSPACE STATUS ===" && echo
   echo "Files by status:"
   echo "  complete: $(ls workspace/*_complete*.md 2>/dev/null | wc -l | tr -d ' ')"
   echo "  active:   $(ls workspace/*_active*.md 2>/dev/null | wc -l | tr -d ' ')"
   echo "  blocked:  $(ls workspace/*_blocked*.md 2>/dev/null | wc -l | tr -d ' ')"
   echo
   echo "=== LINEAGE TREES ===" && echo
   python3 << 'PYEOF'
import re
from pathlib import Path
from collections import defaultdict

ws = Path("workspace")
if not ws.exists():
    print("No workspace found")
    exit()

files = {}
children = defaultdict(list)

for p in sorted(ws.glob("*.md")):
    m = re.match(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$', p.stem)
    if m:
        seq, slug, status, parent = m.groups()
        key = f"{seq}_{slug}"
        files[key] = {"path": p.name, "seq": seq, "status": status, "parent": parent}
        if parent:
            for k, f in files.items():
                if f["seq"] == parent:
                    children[k].append(key)
                    break

def print_tree(key, level=0):
    f = files[key]
    marker = {"complete": "+", "active": "~", "blocked": "!"}.get(f["status"], " ")
    print("  " * level + f"[{marker}] {f['path']}")
    for child in sorted(children.get(key, [])):
        print_tree(child, level + 1)

roots = [k for k, f in files.items() if not f["parent"]]
for root in sorted(roots):
    print_tree(root)
    print()
PYEOF
   ```

   **"active" | "blocked" | "complete"** — filter by status:
   ```bash
   ls -la workspace/*_${STATUS}*.md 2>/dev/null || echo "No ${STATUS} files"
   ```

   **A number (e.g., "003")** — show lineage:
   ```bash
   python3 << 'PYEOF'
import re, sys
from pathlib import Path

target = "$SELECTOR"  # Replace with actual number
ws = Path("workspace")

files = {}
for p in sorted(ws.glob("*.md")):
    m = re.match(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$', p.stem)
    if m:
        seq, slug, status, parent = m.groups()
        files[seq] = {"path": p.name, "parent": parent, "slug": slug}

if target not in files:
    print(f"No file with sequence {target}")
    sys.exit(1)

# Trace ancestors
chain = []
current = target
while current and current in files:
    chain.append(current)
    current = files[current]["parent"]
chain.reverse()

print(f"Ancestors (depth {len(chain)}):")
print("  " + " -> ".join(chain))
print()
for seq in chain:
    print(f"  {files[seq]['path']}")

# Find descendants
print(f"\nDescendants of {target}:")
for seq, f in sorted(files.items()):
    if f["parent"] == target:
        print(f"  {f['path']}")
PYEOF
   ```

   **"roots"** — show root files (no parent):
   ```bash
   ls workspace/*.md 2>/dev/null | while read f; do
     [[ ! "$f" =~ _from-[0-9] ]] && basename "$f"
   done
   ```

   **"orphans"** — find broken parent refs:
   ```bash
   for f in workspace/*_from-*.md 2>/dev/null; do
     parent=$(basename "$f" | grep -oE '_from-[0-9]+' | grep -oE '[0-9]+')
     if ! ls workspace/${parent}_*.md &>/dev/null; then
       echo "Orphan: $(basename $f) -> missing parent $parent"
     fi
   done
   ```

   **"tags"** — find all Key Findings tags:
   ```bash
   grep -h "^#pattern/\|^#constraint/\|^#decision/\|^#antipattern/\|^#connection/" workspace/*_complete*.md 2>/dev/null | sort -u
   ```

   **"find PATTERN"** — search workspace content:
   ```bash
   grep -rn "PATTERN" workspace/*.md 2>/dev/null
   ```

   **"stats"** — detailed statistics:
   ```bash
   python3 << 'PYEOF'
import re
from pathlib import Path
from collections import defaultdict

ws = Path("workspace")
if not ws.exists():
    print("No workspace found")
    exit()

total = 0
statuses = defaultdict(int)
max_depth = 0
files = {}

for p in sorted(ws.glob("*.md")):
    m = re.match(r'^(\d{3})_(.+?)_([^_]+?)(?:_from-(\d{3}))?$', p.stem)
    if m:
        total += 1
        seq, slug, status, parent = m.groups()
        statuses[status] += 1
        files[seq] = parent

# Calculate depths
def get_depth(seq):
    depth = 1
    current = seq
    while files.get(current):
        current = files[current]
        depth += 1
    return depth

for seq in files:
    max_depth = max(max_depth, get_depth(seq))

orphans = sum(1 for seq, parent in files.items() if parent and parent not in files)
roots = sum(1 for seq, parent in files.items() if not parent)

print("Workspace Statistics")
print("=" * 20)
print(f"\nTotal files:     {total}")
print("\nBy status:")
for s in ["complete", "active", "blocked"]:
    print(f"  {s:12} {statuses.get(s, 0)}")
print("\nLineage:")
print(f"  Max depth:     {max_depth}")
print(f"  Root files:    {roots}")
print(f"  Orphans:       {orphans}")
PYEOF
   ```

3. If no workspace folder exists:
   - Report this to user
   - Suggest creating first anchor with `/tether:anchor [task]`

## Output Indicators

For lineage trees:
- `[+]` = complete
- `[~]` = active
- `[!]` = blocked

## Advanced: Full WQL

For power users, the full WQL tool is available at `tether/wql/wql.py`:

```bash
python3 /path/to/tether/wql/wql.py -w ./workspace stat
python3 /path/to/tether/wql/wql.py -w ./workspace graph
python3 /path/to/tether/wql/wql.py -w ./workspace lineage 003 --both
python3 /path/to/tether/wql/wql.py -w ./workspace grep "#pattern/" --status complete
```

Set `WQL_WORKSPACE` to override the default workspace path.
