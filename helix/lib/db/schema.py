"""Data models for Helix.

Core entities:
- Insight: Learned knowledge with effectiveness tracking
- MemoryEdge: Relationships between insights (graph structure)

Note: Plan, Task, and Workspace are handled by Claude Code's native
Task system with metadata. See SKILL.md for the architecture.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Insight:
    """A learned piece of knowledge.

    Content format: "When X, do Y because Z"

    Insights earn their place through demonstrated usefulness.
    The feedback loop tracks effectiveness via use_count and EMA updates.

    NOTE: This dataclass documents the schema but is not instantiated.
    Storage uses raw SQL; retrieval uses _to_dict() in core.py.
    """
    name: str  # Unique kebab-case slug
    content: str  # Full insight text

    # Effectiveness tracking (0-1 scale, EMA updated)
    effectiveness: float = 0.5  # Starts neutral
    use_count: int = 0  # Times injected and received feedback

    # Semantic search (384-dim all-MiniLM-L6-v2)
    embedding: Optional[bytes] = None

    # Tags for categorization (JSON array)
    tags: str = "[]"

    # Timestamps
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None

    # Auto-generated
    id: Optional[int] = None


@dataclass
class MemoryEdge:
    """Relationship between two insights.

    Enables graph traversal for related knowledge.
    Types: similar, solves, causes, co_occurs
    """
    from_name: str
    to_name: str
    rel_type: str  # similar, solves, causes, co_occurs
    weight: float = 1.0  # Capped at 10.0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None


# Legacy alias for backwards compatibility
Memory = Insight
