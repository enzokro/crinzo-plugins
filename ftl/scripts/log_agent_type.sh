#!/usr/bin/env bash
# FTL Agent Type Logging
# Usage: log_agent_type.sh <type>
# Writes agent completion to manifest for eval capture

TYPE=${1:-unknown}
INPUT=$(cat)

# Extract agent ID from hook input (if available)
AGENT_ID=$(echo "$INPUT" | jq -r '.agent_id // "unknown"' 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Ensure cache directory exists
mkdir -p .ftl/cache

# Append to manifest (JSONL format)
echo "{\"ts\":\"$TIMESTAMP\",\"type\":\"$TYPE\",\"agent_id\":\"$AGENT_ID\"}" >> .ftl/cache/agent_manifest.jsonl

exit 0
