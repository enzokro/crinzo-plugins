#!/usr/bin/env bash
#
# Loop Plugin - Session Start Hook
#
# Sets up the environment for the learning system:
# 1. Creates .loop directory for state
# 2. Records plugin root for library imports
# 3. Initializes database if needed
# 4. Sets up Python environment
#

set -euo pipefail

# Get plugin root (where this script lives, minus /scripts)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

# State directory
LOOP_DIR=".loop"

# Create state directory
mkdir -p "$LOOP_DIR"

# Record plugin root for imports
echo "$PLUGIN_ROOT" > "$LOOP_DIR/plugin_root"

# Initialize database (idempotent)
if command -v python3 &> /dev/null; then
    # Quick init - just ensure tables exist
    python3 -c "
import sys
sys.path.insert(0, '$PLUGIN_ROOT/lib')
from db.connection import init_db
init_db()
" 2>/dev/null || true
fi

# Check for sentence-transformers (for semantic search)
if python3 -c "import sentence_transformers" 2>/dev/null; then
    echo "embeddings: available" > "$LOOP_DIR/status"
else
    echo "embeddings: unavailable (install sentence-transformers for semantic search)" > "$LOOP_DIR/status"
fi

# Log session start
echo "$(date -Iseconds) session_start" >> "$LOOP_DIR/sessions.log"

exit 0
