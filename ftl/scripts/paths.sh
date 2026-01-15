#!/bin/bash
# FTL v2 environment configuration

# Get FTL root (directory containing this script's parent)
FTL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

export FTL_ROOT
export FTL_LIB="$FTL_ROOT/lib"
export FTL_AGENTS="$FTL_ROOT/agents"
export FTL_SKILLS="$FTL_ROOT/skills"

# Agent paths (for Task tool registration)
export FTL_AGENT_PLANNER="$FTL_AGENTS/planner.md"
export FTL_AGENT_BUILDER="$FTL_AGENTS/builder.md"
export FTL_AGENT_OBSERVER="$FTL_AGENTS/observer.md"

# Runtime directories
export FTL_WORKSPACE=".ftl/workspace"
export FTL_CACHE=".ftl/cache"
