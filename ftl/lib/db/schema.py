"""Database schema definitions using dataclasses for fastsql."""

from dataclasses import dataclass, field
from typing import Optional
import struct


def embed_to_blob(embedding: tuple) -> bytes:
    """Convert embedding tuple to SQLite BLOB (1536 bytes for 384 floats)."""
    if embedding is None:
        return None
    return struct.pack(f'{len(embedding)}f', *embedding)


def blob_to_embed(blob: bytes) -> tuple:
    """Convert BLOB back to embedding tuple."""
    if blob is None:
        return None
    count = len(blob) // 4
    return struct.unpack(f'{count}f', blob)


@dataclass
class Memory:
    """Unified failures + patterns (polymorphic storage)."""
    id: int = field(default=None)
    name: str = ""                    # kebab-case slug, UNIQUE
    type: str = "failure"             # "failure" | "pattern"
    trigger: str = ""                 # Error message or condition
    resolution: str = ""              # Fix (failure) or insight (pattern)
    match: Optional[str] = None       # Regex for log matching (failures only)
    cost: int = 0                     # Tokens spent (failure) or saved (pattern)
    source: str = "[]"                # JSON: workspace IDs
    created_at: str = ""              # ISO timestamp
    last_accessed: str = ""           # ISO timestamp
    access_count: int = 0
    times_helped: int = 0
    times_failed: int = 0
    importance: float = 0.0           # Pre-computed ranking score
    related_typed: str = "{}"         # JSON: {rel_type: [names]}
    cross_relationships: str = "{}"   # JSON: {rel_type: [names]}
    embedding: Optional[bytes] = None # BLOB: 1536 bytes (384 floats)


@dataclass
class MemoryEdge:
    """Graph edges for BFS traversal of memory relationships."""
    id: int = field(default=None)
    from_id: int = 0                  # FK -> memories.id
    to_id: int = 0                    # FK -> memories.id
    rel_type: str = "co_occurs"       # co_occurs|causes|solves|prerequisite|variant
    weight: float = 0.8               # Edge weight for path pruning
    created_at: str = ""


@dataclass
class Campaign:
    """Campaign with embedded tasks (DAG structure)."""
    id: int = field(default=None)
    objective: str = ""
    framework: Optional[str] = None
    status: str = "active"            # active|complete
    created_at: str = ""
    completed_at: Optional[str] = None
    tasks: str = "[]"                 # JSON: [{seq, slug, type, depends, status}]
    summary: str = "{}"               # JSON: completion summary
    fingerprint: str = "{}"           # JSON: similarity fingerprint
    patterns_extracted: str = "[]"    # JSON: pattern names
    objective_embedding: Optional[bytes] = None  # BLOB for similarity


@dataclass
class Workspace:
    """Workspace execution record (replaces XML files)."""
    id: int = field(default=None)
    workspace_id: str = ""            # "001-slug" format, UNIQUE
    campaign_id: int = 0              # FK -> campaigns.id
    seq: str = ""
    slug: str = ""
    status: str = "active"            # active|complete|blocked
    created_at: str = ""
    completed_at: Optional[str] = None
    blocked_at: Optional[str] = None
    objective: str = ""
    delta: str = "[]"                 # JSON: files to modify
    verify: str = ""
    verify_source: Optional[str] = None
    budget: int = 5
    framework: Optional[str] = None
    framework_confidence: float = 1.0
    idioms: str = "{}"                # JSON: {required, forbidden}
    prior_knowledge: str = "{}"       # JSON: injected memories
    lineage: str = "{}"               # JSON: parent references
    delivered: str = ""
    utilized_memories: str = "[]"     # JSON: feedback tracking
    code_contexts: str = "[]"         # JSON: code snapshots
    preflight: str = "[]"             # JSON: preflight checks


@dataclass
class Archive:
    """Lightweight archive for find_similar() on completed campaigns."""
    id: int = field(default=None)
    campaign_id: int = 0
    objective: str = ""
    objective_preview: str = ""       # First 100 chars
    framework: Optional[str] = None
    completed_at: str = ""
    fingerprint: str = "{}"
    objective_embedding: Optional[bytes] = None
    outcome: str = "complete"         # complete|partial
    summary: str = "{}"
    patterns_extracted: str = "[]"


@dataclass
class Exploration:
    """Aggregated explorer outputs."""
    id: int = field(default=None)
    campaign_id: Optional[int] = None
    objective: str = ""
    git_sha: str = ""
    created_at: str = ""
    structure: str = "{}"             # JSON: structure mode
    pattern: str = "{}"               # JSON: pattern mode
    memory: str = "{}"                # JSON: memory mode
    delta: str = "{}"                 # JSON: delta mode
    modes_completed: int = 0
    status: str = "pending"


@dataclass
class PhaseState:
    """Workflow phase tracking (singleton pattern)."""
    id: int = field(default=None)
    phase: str = "none"
    started_at: Optional[str] = None
    transitions: str = "[]"           # JSON: [{from, to, at}]


@dataclass
class Event:
    """Append-only event log for audit trail."""
    id: int = field(default=None)
    event_type: str = ""
    timestamp: str = ""
    metadata: str = "{}"


@dataclass
class ExplorerResult:
    """Individual explorer mode output (staging before aggregation)."""
    id: int = field(default=None)
    session_id: str = ""           # UUID linking parallel explorers
    mode: str = ""                 # structure|pattern|memory|delta
    status: str = "pending"        # pending|ok|partial|error
    result: str = "{}"             # JSON: mode-specific output
    created_at: str = ""


@dataclass
class Plan:
    """Task plan from planner agent."""
    id: int = field(default=None)
    campaign_id: Optional[int] = None
    objective: str = ""
    framework: Optional[str] = None
    idioms: str = "{}"             # JSON: {required, forbidden}
    tasks: str = "[]"              # JSON: task array
    created_at: str = ""
    status: str = "active"         # active|executed|superseded


@dataclass
class Benchmark:
    """Performance benchmark results."""
    id: int = field(default=None)
    run_id: str = ""               # UUID for benchmark run
    metric: str = ""               # memory_size|query_time|etc
    value: float = 0.0
    metadata: str = "{}"           # JSON
    created_at: str = ""
