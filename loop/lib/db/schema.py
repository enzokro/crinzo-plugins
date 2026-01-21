"""Memory schema - the essential data structure."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Memory:
    """A single unit of learned knowledge.

    This is the atomic unit of the learning system. Each memory represents
    either a failure (something that hurt) or a pattern (something that helped).

    The effectiveness is earned through use - memories that actually help
    get boosted, memories that don't fade away.
    """

    # Identity
    id: Optional[int] = None
    name: str = ""                    # kebab-case identifier
    type: str = "failure"             # "failure" or "pattern"

    # The knowledge itself
    trigger: str = ""                 # when does this apply?
    resolution: str = ""              # what do you do about it?

    # Semantic meaning (for similarity search)
    embedding: Optional[bytes] = None  # 384-dim float32 as blob

    # Effectiveness tracking (the feedback loop)
    helped: int = 0                   # times this actually worked
    failed: int = 0                   # times this was injected but unused

    # Metadata
    created_at: str = ""
    last_used: Optional[str] = None
    source: str = ""                  # where did this come from?

    @property
    def effectiveness(self) -> float:
        """How often does this memory actually help when injected?

        Returns 0.5 (neutral) when no feedback yet.
        Approaches 1.0 for always-helpful memories.
        Approaches 0.0 for never-helpful memories.
        """
        total = self.helped + self.failed
        if total == 0:
            return 0.5  # no data yet, neutral prior
        return self.helped / total

    @property
    def total_uses(self) -> int:
        """Total times this memory has been injected."""
        return self.helped + self.failed

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "trigger": self.trigger,
            "resolution": self.resolution,
            "helped": self.helped,
            "failed": self.failed,
            "effectiveness": round(self.effectiveness, 3),
            "total_uses": self.total_uses,
            "created_at": self.created_at,
            "last_used": self.last_used,
            "source": self.source,
        }
