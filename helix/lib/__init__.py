"""Helix - Advanced Self-Learning Orchestrator.

Core modules:
- memory: Semantic memory with feedback loop
- context: Builder context building
- tasks: Task operation helpers for orchestrator
- dag_utils: DAG utility functions (cycle detection, stall checking)

Architecture: Prose-driven orchestration (SKILL.md) with memory enrichment.
SKILL.md is the orchestrator; code provides mechanical utilities.
Task management is handled by Claude Code's native Task system.
"""

__version__ = "2.0.0"
