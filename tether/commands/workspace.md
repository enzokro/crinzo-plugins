---
description: Query the cognitive workspace. Shows active tasks, lineage, and available context.
allowed-tools: Bash, Read, Glob, Grep
---

# Workspace Query

Query the cognitive workspace for this project.

## Protocol

1. List workspace contents:
   ```bash
   ls -la workspace/ 2>/dev/null || echo "No workspace folder found"
   ```

2. Parse $ARGUMENTS for query type:

   **Status queries:**
   - "active" → show only `*_active*` files
   - "blocked" → show only `*_blocked*` files
   - "complete" → show only `*_complete*` files

   **Lineage queries:**
   - A number (e.g., "003") → show that file and its lineage chain
   - "chain" → show all lineage chains with depth > 1
   - "roots" → show all root files (no `_from-NNN` suffix)
   - "orphans" → show files referencing non-existent parents

   **Content queries:**
   - "find PATTERN" → grep workspace files for PATTERN
   - "tags" → find all #pattern/, #insight/, #connection/ tags
   - "friction" → search for friction/blocked mentions

   **Stats:**
   - "stats" → show workspace statistics (total, by status, depth)

3. Execute appropriate query:

   For lineage chains:
   ```bash
   # Find all files with _from- suffix and trace ancestry
   grep -l "_from-" workspace/*.md 2>/dev/null
   ```

   For content search:
   ```bash
   grep -r "PATTERN" workspace/*.md 2>/dev/null
   ```

   For tags:
   ```bash
   grep -h "#pattern/\|#insight/\|#connection/" workspace/*.md 2>/dev/null
   ```

4. Report findings with structure

5. If no workspace folder exists:
   - Report this to user
   - Suggest creating first anchor with `/tether:anchor [task]`

## Output Format

**For status query:**
```
WORKSPACE STATUS

Active:
  - 003_feature-x_active (from 001)

Blocked:
  - 002_api-auth_blocked

Complete:
  - 001_initial-setup_complete
  - 004_health-check_complete_from-001

Next sequence: 005
```

**For lineage query:**
```
LINEAGE: 003

Ancestors:
  001_initial-setup_complete
    └── 003_feature-x_active

Descendants:
  (none yet)

Chain depth: 2
```

**For content query:**
```
CONTENT SEARCH: "friction"

001_tether-friction-analysis_complete.md:
  Line 45: - F1 identified: "NNN Format Drift"
  Line 52: - Root cause: instruction buried AFTER sequence

002_enforce-nnn-format_complete_from-001.md:
  Line 12: Builds on 001: Implements P1 friction fix

Found: 2 files, 3 matches
```

**For tags query:**
```
KNOWLEDGE TAGS

#pattern/constraint-discipline (001_constraint-refactor)
#pattern/section-aware-grep (025_wql)
#insight/traces-as-work (024_research-dialect)
#connection/lineage-to-visualization (025_wql)

Total: 4 tags across 3 files
```

**For stats query:**
```
WORKSPACE STATS

Total files: 25
  complete: 22
  active:   2
  blocked:  1

Lineage:
  Max depth: 4 (001 → 002 → 003 → 004)
  Root files: 14
  With lineage: 8

Recent: 025_wql_complete (1 hour ago)
```
