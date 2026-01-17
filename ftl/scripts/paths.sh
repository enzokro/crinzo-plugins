#!/bin/bash
# FTL v2 environment configuration with existence checks

# Get FTL root (directory containing this script's parent)
FTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Validate FTL_ROOT exists
if [ ! -d "$FTL_ROOT" ]; then
    echo "[ftl] Error: FTL_ROOT does not exist: $FTL_ROOT" >&2
    exit 1
fi

export FTL_ROOT

# Set paths with existence validation
if [ -d "$FTL_ROOT/lib" ]; then
    export FTL_LIB="$FTL_ROOT/lib"
else
    echo "[ftl] Warning: lib directory not found at $FTL_ROOT/lib" >&2
fi

if [ -d "$FTL_ROOT/agents" ]; then
    export FTL_AGENTS="$FTL_ROOT/agents"
else
    echo "[ftl] Warning: agents directory not found at $FTL_ROOT/agents" >&2
fi

if [ -d "$FTL_ROOT/skills" ]; then
    export FTL_SKILLS="$FTL_ROOT/skills"
else
    echo "[ftl] Warning: skills directory not found at $FTL_ROOT/skills" >&2
fi

# Agent paths (for Task tool registration)
# Only export if files exist
if [ -f "$FTL_AGENTS/planner.md" ]; then
    export FTL_AGENT_PLANNER="$FTL_AGENTS/planner.md"
fi

if [ -f "$FTL_AGENTS/builder.md" ]; then
    export FTL_AGENT_BUILDER="$FTL_AGENTS/builder.md"
fi

if [ -f "$FTL_AGENTS/observer.md" ]; then
    export FTL_AGENT_OBSERVER="$FTL_AGENTS/observer.md"
fi

# Runtime directories
export FTL_WORKSPACE=".ftl/workspace"
export FTL_CACHE=".ftl/cache"
