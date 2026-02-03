#!/bin/bash
# SubagentStop hook - extracts learning candidates from helix agent transcripts
#
# Reads hook input from stdin, checks if it's a helix agent completion,
# and extracts learning candidates to .helix/learning-queue/
#
# Returns:
#   {} - always (side effects only)

set -euo pipefail

# Get helix root from environment or script location
HELIX_ROOT="${HELIX_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"

# Read input from stdin
INPUT=$(cat)

# Quick check: is this a helix agent?
AGENT_TYPE=$(echo "$INPUT" | jq -r '.agent_type // ""')
case "$AGENT_TYPE" in
    helix:helix-*)
        # Process with Python - export project dir for consistent .helix path resolution
        export HELIX_PROJECT_DIR="${HELIX_PROJECT_DIR:-$PWD}"
        export HELIX_DB_PATH="${HELIX_DB_PATH:-$PWD/.helix/helix.db}"
        echo "$INPUT" | python3 "$HELIX_ROOT/lib/hooks/extract_learning.py"
        ;;
    *)
        # Not a helix agent
        echo "{}"
        ;;
esac
