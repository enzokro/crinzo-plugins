"""Data models for Helix.

Core entities:
- Memory: Learned failures and patterns with embeddings
- MemoryEdge: Relationships between memories (graph structure)
- Exploration: Gathered context for planning
- Plan: Task decomposition with dependencies
- Task: Individual executable unit
- Workspace: Execution context for a task
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


@dataclass
class Task:
    """A single executable unit within a plan.

    Tasks form a DAG via the 'depends' field.
    """
    seq: str  # "001", "002", etc.
    slug: str  # Human-readable identifier
    objective: str  # What this task accomplishes

    # Scope
    delta: List[str] = field(default_factory=list)  # Files to modify
    verify: str = ""  # Command to verify completion

    # Dependencies (DAG)
    depends: str = "none"  # "none", "001", or "001,002"

    # Constraints
    budget: int = 7  # Tool call budget

    # Status
    status: str = "pending"  # pending, active, complete, blocked

    # Results
    delivered: str = ""
    blocked_reason: str = ""
    utilized_memories: List[str] = field(default_factory=list)


@dataclass
class Plan:
    """Task decomposition for an objective.

    The planner produces this, the orchestrator consumes it.
    """
    objective: str
    framework: Optional[str] = None
    idioms: dict = field(default_factory=dict)

    tasks: List[Task] = field(default_factory=list)

    status: str = "active"  # active, executing, complete, failed
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None

    @property
    def task_count(self) -> int:
        return len(self.tasks)

    def get_task(self, seq: str) -> Optional[Task]:
        for t in self.tasks:
            if t.seq == seq:
                return t
        return None

    def ready_tasks(self) -> List[Task]:
        """Tasks whose dependencies are all complete."""
        complete_seqs = {t.seq for t in self.tasks if t.status == "complete"}
        ready = []
        for t in self.tasks:
            if t.status != "pending":
                continue
            deps = [d.strip() for d in t.depends.split(",") if d.strip() and d.strip() != "none"]
            if all(d in complete_seqs for d in deps):
                ready.append(t)
        return ready


@dataclass
class Workspace:
    """Execution context for a single task.

    Contains everything the builder needs.
    """
    task_seq: str
    task_slug: str
    objective: str

    # Scope
    delta: List[str] = field(default_factory=list)
    verify: str = ""
    budget: int = 7

    # Context
    framework: Optional[str] = None
    idioms: dict = field(default_factory=dict)

    # Memory injection
    failures: List[dict] = field(default_factory=list)
    patterns: List[dict] = field(default_factory=list)

    # Lineage (what previous tasks delivered)
    lineage: dict = field(default_factory=dict)

    # Status
    status: str = "active"  # active, complete, blocked
    delivered: str = ""
    utilized_memories: List[str] = field(default_factory=list)

    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    id: Optional[int] = None
