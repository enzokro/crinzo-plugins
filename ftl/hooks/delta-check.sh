#!/bin/bash
# Delta enforcement hook for tether
# Blocks Edit/Write to files not declared in Delta

WORKSPACE_DIR="${WQL_WORKSPACE:-workspace}"

# Find active workspace file
ACTIVE=$(ls "$WORKSPACE_DIR"/*_active*.md 2>/dev/null | head -1)
[ -z "$ACTIVE" ] && exit 0  # No active workspace = no constraint

# Parse Delta from workspace
DELTA=$(grep -A5 "^## Anchor" "$ACTIVE" | grep "^Delta:" | sed 's/^Delta:[[:space:]]*//')
[ -z "$DELTA" ] && exit 0  # No Delta = no constraint

# Get target file from tool input (passed as $TOOL_INPUT JSON)
TARGET=$(echo "$TOOL_INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"file_path"[[:space:]]*:[[:space:]]*"//' | sed 's/"$//')
[ -z "$TARGET" ] && exit 0  # Can't determine target

# Normalize to basename for simple matching
TARGET_BASE=$(basename "$TARGET")

# Check if target is in Delta (simple substring match)
if echo "$DELTA" | grep -qi "$TARGET_BASE"; then
  exit 0  # Allowed
fi

# Check if Delta contains "workspace" and target is in workspace/
if echo "$DELTA" | grep -qi "workspace" && echo "$TARGET" | grep -q "workspace/"; then
  exit 0  # Workspace files always allowed during tether work
fi

# Violation
echo "DELTA VIOLATION: $TARGET_BASE not in declared scope"
echo "Delta: $DELTA"
echo "Use /tether:anchor to update scope or modify Delta in workspace file"
exit 1
