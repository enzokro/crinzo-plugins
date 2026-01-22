#!/bin/bash
# Arc session initialization

set -e

# Create arc directory if needed
mkdir -p .arc

# Store plugin root for library access
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
    echo "$CLAUDE_PLUGIN_ROOT" > .arc/plugin_root
fi

# Initialize database (happens automatically on first access)
# Just verify Python is available
python3 --version > /dev/null 2>&1 || {
    echo "Warning: Python 3 not found. Arc requires Python 3."
    exit 0
}

# Check for sentence-transformers (optional but recommended)
python3 -c "import sentence_transformers" 2>/dev/null || {
    echo "Note: sentence-transformers not installed. Semantic search will use fallback."
}

echo "Arc initialized."
