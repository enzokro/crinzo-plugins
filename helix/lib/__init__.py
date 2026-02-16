"""Helix - Advanced Self-Learning Orchestrator.

Core modules:
- memory: Semantic memory with feedback loop (core, embeddings)
- db: SQLite connection with WAL mode and schema migrations
- injection: Insight injection for agents (inject_context, batch_inject, format_prompt)
- extraction: Completion processing for insight extraction
- build_loop: Build orchestration (wait, wave synthesis, DAG utilities)
- paths: Helix directory resolution
- hooks: SubagentStop and SessionEnd handlers

Architecture: Prose-driven orchestration (SKILL.md) with memory enrichment.
SKILL.md is the orchestrator; code provides mechanical utilities.
Task management is handled by Claude Code's native Task system.
"""

__version__ = "2.0.0"
