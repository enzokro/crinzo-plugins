#!/bin/bash
# capture_delta.sh - Cache Cognition State + Delta files after each agent
# Called by SubagentStop hook. Uses CLAUDE_PROJECT_DIR if available.
#
# Caches TWO things:
#   1. cognition_state.md - Phase model, inherited knowledge, operational state
#   2. delta_contents.md - Delta file contents for builder/learner
#
# The cognition cache is not just state — it's how agents inherit knowledge.
# Without it, downstream agents re-learn what upstream agents already knew.

set -e

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-.}"
CACHE_DIR="$PROJECT_DIR/.ftl/cache"
WORKSPACE_DIR="$PROJECT_DIR/.ftl/workspace"

mkdir -p "$CACHE_DIR"

# Consume stdin (hook input)
cat > /dev/null

# ============================================================
# Part 1: Update cognition_state.md (ALWAYS runs)
# ============================================================
LAST_SEQ=$(ls "$WORKSPACE_DIR/" 2>/dev/null | grep -oE '^[0-9]+' | sort -n | tail -1)
[ -z "$LAST_SEQ" ] && LAST_SEQ="000"

ACTIVE=$(ls "$WORKSPACE_DIR/"*_active*.xml 2>/dev/null | xargs -I{} basename {} 2>/dev/null | tr '\n' ', ' | sed 's/,$//' || echo "none")
[ -z "$ACTIVE" ] && ACTIVE="none"

RECENT=$(ls -t "$WORKSPACE_DIR/"*_complete*.xml 2>/dev/null | head -3 | xargs -I{} basename {} 2>/dev/null | tr '\n' ', ' | sed 's/,$//' || echo "none")
[ -z "$RECENT" ] && RECENT="none"

# Extract recent learnings from the most recently completed workspace
# This enables within-run knowledge transfer: task 002 sees what task 001 learned
RECENT_LEARNINGS=""
RECENT_COMPLETE=$(ls -t "$WORKSPACE_DIR/"*_complete*.xml 2>/dev/null | head -1)
if [ -n "$RECENT_COMPLETE" ] && [ -f "$RECENT_COMPLETE" ]; then
  # Extract the <delivered> element from XML workspace
  DELIVERED=$(python3 -c "
import xml.etree.ElementTree as ET
tree = ET.parse('$RECENT_COMPLETE')
d = tree.find('.//delivered')
print(d.text if d is not None and d.text else '')
" 2>/dev/null | head -20 | sed 's/^/  /')
  if [ -n "$DELIVERED" ]; then
    TASK_NAME=$(basename "$RECENT_COMPLETE" | sed 's/_complete.xml//' | sed 's/^[0-9]*_//')
    RECENT_LEARNINGS=$(cat << LEARNING
## Recent Learnings

From $(basename "$RECENT_COMPLETE"):
$DELIVERED

LEARNING
)
  fi
fi

# Campaign context
CAMPAIGN_OBJ=""
if [ -f "$PROJECT_DIR/.ftl/campaign.json" ]; then
  CAMPAIGN_OBJ=$(cat "$PROJECT_DIR/.ftl/campaign.json" 2>/dev/null | jq -r '.objective // empty' 2>/dev/null || echo "")
fi

cat > "$CACHE_DIR/cognition_state.md" << EOF
# Cognition State
*Updated: $(date -u +%Y-%m-%dT%H:%M:%SZ)*

## Phase Model

You inherit knowledge from prior phases. You do not re-learn it.

| Phase | Agent | Output |
|-------|-------|--------|
| LEARNING | planner | task breakdown, verification commands |
| SCOPING | router | Delta, Path, precedent |
| EXECUTION | builder | code within Delta |
| EXTRACTION | learner/synthesizer | patterns |

**Category test**: Am I thinking "let me understand X first"?
→ That thought is incoherent. Understanding happened in prior phases.
→ If knowledge feels insufficient, return: "Workspace incomplete: need [X]"

## Inherited Knowledge

Planner analyzed: objective, requirements, verification approach
Router scoped: Delta bounds, data transformation Path, related precedent

**This knowledge is in your workspace file. Read it. Trust it. Execute from it.**

## Operational State

Last sequence: $LAST_SEQ
Active: $ACTIVE
Recent: $RECENT
${CAMPAIGN_OBJ:+Campaign: $CAMPAIGN_OBJ}

${RECENT_LEARNINGS}
## If You're About to Explore

STOP. Ask yourself:
1. Is this file in my Delta? If no → out of scope, do not read
2. Did planner/router already analyze this? If yes → knowledge is in workspace
3. Am I learning or executing? If learning → wrong phase

Exploration during execution costs ~10x more than exploration during routing.
The correct response to insufficient knowledge is escalation, not exploration.
EOF

# ============================================================
# Part 2: Cache Delta contents (only if workspace exists)
# ============================================================

# Clear stale Delta cache
rm -f "$CACHE_DIR/delta_contents.md" 2>/dev/null || true

# Find workspace (prefer active, fall back to most recent complete)
WORKSPACE=$(find "$WORKSPACE_DIR" -name "*_active*.xml" 2>/dev/null | head -1)
[ -z "$WORKSPACE" ] && WORKSPACE=$(ls -t "$WORKSPACE_DIR/"*_complete*.xml 2>/dev/null | head -1)
[ -z "$WORKSPACE" ] && exit 0

# Extract Delta and Delivered from XML using Python
python3 << EOF
import xml.etree.ElementTree as ET
from pathlib import Path
import datetime

workspace = Path("$WORKSPACE")
cache_dir = Path("$CACHE_DIR")

tree = ET.parse(workspace)
root = tree.getroot()

# Extract delta files
delta_files = [d.text for d in root.findall('.//implementation/delta') if d.text]

# Extract delivered content for cognition state
delivered = root.find('.//delivered')
delivered_text = delivered.text if delivered is not None and delivered.text else ''

# Write delta contents
if delta_files:
    with open(cache_dir / 'delta_contents.md', 'w') as f:
        f.write('# Delta File Contents (Cached)\n\n')
        f.write(f'Cached at: {datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")}\n')
        f.write(f'Source workspace: {workspace}\n\n')
        f.write('**Use these contents instead of re-reading the files.**\n\n')

        for delta_file in delta_files:
            path = Path(delta_file)
            if path.exists():
                f.write(f'## {delta_file}\n')
                f.write('```\n')
                f.write(path.read_text())
                f.write('\n```\n\n')

# Update cognition state with delivered if present
if delivered_text:
    task_name = workspace.stem.replace('_active', '').replace('_complete', '')
    print(f"DELIVERED_FROM={workspace.name}")
    print(f"DELIVERED_CONTENT={delivered_text[:500]}")
EOF

exit 0
