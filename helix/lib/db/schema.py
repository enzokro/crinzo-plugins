"""Data models for Helix.

Core entities:
- Memory: Learned failures and patterns with embeddings
- MemoryEdge: Relationships between memories (graph structure)
- Exploration: Gathered context for planning

Note: Plan, Task, and Workspace are now handled by Claude Code's native
Task system with metadata. See SKILL.md for the new architecture.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Memory:
    """A learned piece of knowledge - failure or pattern.

    Memories earn their place through demonstrated usefulness.
    The feedback loop tracks helped/failed to rank by effectiveness.
    """
    name: str
    type: str  # "failure" or "pattern"
    trigger: str  # When does this apply?
    resolution: str  # What do you do about it?

    # Effectiveness tracking (the learning signal)
    helped: int = 0
    failed: int = 0

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
    def total_uses(self) -> int:
        return self.helped + self.failed


@dataclass
class MemoryEdge:
    """Relationship between two memories.

    Enables graph traversal for related knowledge.
    Types: co_occurs, causes, solves, similar
    """
    from_name: str
    to_name: str
    rel_type: str  # co_occurs, causes, solves, similar
    weight: float = 1.0

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None


@dataclass
class Exploration:
    """Gathered context from exploring the codebase.

    The explorer produces this, the planner consumes it.
    """
    objective: str

    # Structure: what exists
    directories: dict = field(default_factory=dict)
    entry_points: List[str] = field(default_factory=list)
    test_patterns: List[str] = field(default_factory=list)

    # Patterns: how things work
    framework: Optional[str] = None
    framework_confidence: float = 0.0
    idioms: dict = field(default_factory=dict)  # {required: [], forbidden: []}

    # Memory: what we know
    relevant_failures: List[dict] = field(default_factory=list)
    relevant_patterns: List[dict] = field(default_factory=list)

    # Targets: what to change
    target_files: List[str] = field(default_factory=list)
    target_functions: List[dict] = field(default_factory=list)

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None
