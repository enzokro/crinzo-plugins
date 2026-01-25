"""Data models for Helix.

Core entities:
- Memory: Learned failures, patterns, and systemic issues
- MemoryEdge: Relationships between memories (graph structure)

Note: Plan, Task, and Workspace are handled by Claude Code's native
Task system with metadata. See SKILL.md for the architecture.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Memory:
    """A learned piece of knowledge.

    Types:
    - failure: Something that went wrong and how to fix it
    - pattern: A successful approach to apply
    - systemic: A recurring issue (3+ occurrences)

    Memories earn their place through demonstrated usefulness.
    The feedback loop tracks helped/failed to rank by effectiveness.
    """
    name: str
    type: str  # "failure", "pattern", or "systemic"
    trigger: str  # When does this apply?
    resolution: str  # What do you do about it?

    # Effectiveness tracking (the learning signal)
    helped: float = 0
    failed: float = 0

    # Semantic search
    embedding: Optional[bytes] = None

    # Metadata
    source: str = ""  # Where this came from
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = None

    # Auto-generated
    id: Optional[int] = None

    @property
    def effectiveness(self) -> float:
        """How often does this memory actually help?"""
        total = self.helped + self.failed
        if total == 0:
            return 0.5  # Neutral until proven
        return self.helped / total

    @property
    def total_uses(self) -> float:
        return self.helped + self.failed


@dataclass
class MemoryEdge:
    """Relationship between two memories.

    Enables graph traversal for related knowledge.
    Types: solves, co_occurs, similar, causes
    """
    from_name: str
    to_name: str
    rel_type: str  # solves, co_occurs, similar, causes
    weight: float = 1.0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None
