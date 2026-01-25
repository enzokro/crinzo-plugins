#!/usr/bin/env python3
"""Orchestrator-level metacognition for Helix.

Provides meta-level reasoning about the BUILD phase:
- Track task completion velocity
- Detect systemic failure patterns
- Recommend abort/replan when stuck
- Persist state across session boundaries

This is ORCHESTRATOR-level awareness, not builder-level.
The old approach (assess_approach) was advisory and isolated.
This new approach integrates with the state machine for enforcement.

Usage:
    from lib.memory.meta import OrchestratorMeta

    meta = OrchestratorMeta.load(objective)

    # After each task completes
    action = meta.on_task_complete(
        task_id="task-123",
        status="delivered",
        duration_ms=15000,
        blocked_reason=None
    )

    if action == "SYSTEMIC_FAILURE":
        # Same failure pattern 3+ times - trigger replan
        orchestrator.transition("stalled", {"reason": "systemic_failure"})

    # Check if we should abort
    should_abort, reason = meta.should_abort()
    if should_abort:
        orchestrator.transition("stalled", {"reason": reason})

    # Get health report
    report = meta.get_health_report()
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any


@dataclass
class TaskAttempt:
    """Record of a single task completion attempt."""
    task_id: str
    status: str  # "delivered", "blocked"
    duration_ms: int
    blocked_reason: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class OrchestratorMeta:
    """Tracks orchestrator's own state across the BUILD phase.

    Persisted to .helix/meta_state.json for session recovery.
    Integrates with state machine for auto-recovery decisions.
    """
    objective: str
    task_attempts: Dict[str, List[TaskAttempt]] = field(default_factory=dict)
    blocked_reasons: List[str] = field(default_factory=list)
    velocity: List[int] = field(default_factory=list)  # ms per task
    systemic_patterns: List[str] = field(default_factory=list)
    session_start: str = field(default_factory=lambda: datetime.now().isoformat())

    def on_task_complete(
        self,
        task_id: str,
        status: str,
        duration_ms: int,
        blocked_reason: Optional[str] = None
    ) -> str:
        """Called after each task completes. Returns action recommendation.

        Returns one of:
            "CONTINUE" - proceed normally
            "SYSTEMIC_FAILURE" - same failure pattern 3+ times, trigger replan
            "VELOCITY_DECAY" - getting slower, consider abort
            "HEALTHY" - making good progress
        """
        attempt = TaskAttempt(
            task_id=task_id,
            status=status,
            duration_ms=duration_ms,
            blocked_reason=blocked_reason
        )

        if task_id not in self.task_attempts:
            self.task_attempts[task_id] = []
        self.task_attempts[task_id].append(attempt)

        self.velocity.append(duration_ms)

        if status == "blocked" and blocked_reason:
            self.blocked_reasons.append(blocked_reason)

            # Extract and track pattern
            pattern = self._extract_pattern(blocked_reason)
            if pattern:
                self.systemic_patterns.append(pattern)
                if self._same_pattern_count(pattern) >= 3:
                    self._persist()
                    return "SYSTEMIC_FAILURE"

        # Check for velocity decay
        if self._is_velocity_decaying():
            self._persist()
            return "VELOCITY_DECAY"

        self._persist()
        return "CONTINUE"

    def _extract_pattern(self, reason: str) -> Optional[str]:
        """Extract generalizable pattern from blocked reason.

        Maps common failure symptoms to pattern categories.
        """
        patterns = [
            ("import", "import_error"),
            ("not found", "file_not_found"),
            ("permission", "permission_error"),
            ("syntax", "syntax_error"),
            ("type", "type_error"),
            ("timeout", "timeout"),
            ("out of scope", "scope_violation"),
            ("delta", "scope_violation"),
            ("circular", "circular_dependency"),
            ("test", "test_failure"),
            ("verify", "verify_failure"),
            ("fixture", "fixture_error"),
            ("database", "database_error"),
            ("connection", "connection_error"),
            ("authentication", "auth_error"),
            ("authorization", "auth_error"),
        ]

        reason_lower = reason.lower()
        for keyword, pattern in patterns:
            if keyword in reason_lower:
                return pattern
        return None

    def _same_pattern_count(self, pattern: str) -> int:
        """Count occurrences of the same pattern."""
        return self.systemic_patterns.count(pattern)

    def _is_velocity_decaying(self) -> bool:
        """Check if task completion is slowing down significantly.

        A 2x slowdown over 3 tasks suggests something is wrong.
        """
        if len(self.velocity) < 3:
            return False

        recent = self.velocity[-3:]
        # Check if latest is more than 2x the earliest of recent
        if recent[-1] > 2 * recent[0] and recent[-1] > 30000:  # > 30s and 2x slower
            return True
        return False

    def should_abort(self) -> Tuple[bool, str]:
        """Check if BUILD phase should abort.

        Returns:
            (should_abort, reason)
        """
        # Calculate stats
        total_tasks = len(self.task_attempts)
        blocked_count = sum(
            1 for attempts in self.task_attempts.values()
            for a in attempts if a.status == "blocked"
        )

        # Too many blocked tasks (>60%)
        if total_tasks >= 3 and blocked_count / total_tasks > 0.6:
            return True, f"Majority of tasks blocked ({blocked_count}/{total_tasks})"

        # Too many systemic failures
        pattern_counts = {}
        for p in self.systemic_patterns:
            pattern_counts[p] = pattern_counts.get(p, 0) + 1

        for pattern, count in pattern_counts.items():
            if count >= 5:
                return True, f"Systemic failure pattern: {pattern} ({count} occurrences)"

        # Velocity collapse
        if len(self.velocity) >= 5:
            avg_early = sum(self.velocity[:2]) / 2
            avg_late = sum(self.velocity[-2:]) / 2
            if avg_late > 5 * avg_early and avg_late > 60000:  # 5x slower, > 1min
                return True, "Task completion velocity collapsed"

        return False, ""

    def get_health_report(self) -> dict:
        """Generate health report for current session."""
        total_attempts = sum(len(a) for a in self.task_attempts.values())
        blocked = sum(
            1 for attempts in self.task_attempts.values()
            for a in attempts if a.status == "blocked"
        )
        delivered = total_attempts - blocked

        avg_velocity = sum(self.velocity) / len(self.velocity) if self.velocity else 0

        # Pattern analysis
        pattern_counts = {}
        for p in self.systemic_patterns:
            pattern_counts[p] = pattern_counts.get(p, 0) + 1

        should_abort, abort_reason = self.should_abort()

        return {
            "objective": self.objective[:50] + "..." if len(self.objective) > 50 else self.objective,
            "session_start": self.session_start,
            "total_tasks": len(self.task_attempts),
            "total_attempts": total_attempts,
            "delivered": delivered,
            "blocked": blocked,
            "success_rate": delivered / total_attempts if total_attempts else 0,
            "avg_velocity_ms": int(avg_velocity),
            "systemic_patterns": pattern_counts,
            "should_abort": should_abort,
            "abort_reason": abort_reason if should_abort else None
        }

    def get_retry_count(self, task_id: str) -> int:
        """Get number of attempts for a specific task."""
        return len(self.task_attempts.get(task_id, []))

    def get_blocked_tasks(self) -> List[str]:
        """Get list of task IDs that are blocked."""
        blocked = []
        for task_id, attempts in self.task_attempts.items():
            if any(a.status == "blocked" for a in attempts):
                blocked.append(task_id)
        return blocked

    def get_active_warnings(self) -> Optional[str]:
        """Get warning message for systemic patterns detected 3+ times.

        Returns a warning string if a pattern has been seen 3+ times,
        suitable for injection into builder context. Returns None if
        no concerning patterns detected.

        This enables direct pattern injection - the warning is surfaced
        to builders so they can address systemic issues proactively.
        """
        if not self.systemic_patterns:
            return None

        # Count pattern occurrences
        pattern_counts = {}
        for p in self.systemic_patterns:
            pattern_counts[p] = pattern_counts.get(p, 0) + 1

        # Find patterns with 3+ occurrences
        concerning = [(p, c) for p, c in pattern_counts.items() if c >= 3]
        if not concerning:
            return None

        # Return most frequent pattern as warning
        most_frequent = max(concerning, key=lambda x: x[1])
        pattern, count = most_frequent

        return f"Systemic issue detected: {pattern} (seen {count}x). Address this first before proceeding."

    def _persist(self):
        """Save state to disk for session recovery."""
        path = Path.cwd() / ".helix" / "meta_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert to serializable format
        data = {
            "objective": self.objective,
            "session_start": self.session_start,
            "task_attempts": {
                k: [asdict(a) for a in v]
                for k, v in self.task_attempts.items()
            },
            "blocked_reasons": self.blocked_reasons,
            "velocity": self.velocity,
            "systemic_patterns": self.systemic_patterns
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, objective: str) -> "OrchestratorMeta":
        """Load from disk or create new.

        If a state file exists for the same objective, resume from it.
        Otherwise, create fresh state.
        """
        path = Path.cwd() / ".helix" / "meta_state.json"

        if path.exists():
            try:
                data = json.loads(path.read_text())
                # Only resume if same objective
                if data.get("objective") == objective:
                    meta = cls(objective=objective)
                    meta.session_start = data.get("session_start", datetime.now().isoformat())
                    meta.task_attempts = {
                        k: [TaskAttempt(**a) for a in v]
                        for k, v in data.get("task_attempts", {}).items()
                    }
                    meta.blocked_reasons = data.get("blocked_reasons", [])
                    meta.velocity = data.get("velocity", [])
                    meta.systemic_patterns = data.get("systemic_patterns", [])
                    return meta
            except Exception:
                pass

        return cls(objective=objective)

    @classmethod
    def clear(cls) -> bool:
        """Clear meta state file.

        Returns True if file was cleared, False if it didn't exist.
        """
        path = Path.cwd() / ".helix" / "meta_state.json"
        if path.exists():
            path.unlink()
            return True
        return False


def _cli():
    """CLI interface for metacognition operations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Metacognition: orchestrator-level and builder-level awareness"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # health - orchestrator-level health report
    p = subparsers.add_parser("health", help="Show orchestrator health report")
    p.add_argument("--objective", required=True, help="The objective")

    # warnings - get active systemic warnings
    p = subparsers.add_parser("warnings", help="Get active systemic warnings for builder injection")
    p.add_argument("--objective", required=True, help="The objective")

    # complete - record task completion
    p = subparsers.add_parser("complete", help="Record task completion")
    p.add_argument("--objective", required=True)
    p.add_argument("--task-id", required=True)
    p.add_argument("--status", required=True, choices=["delivered", "blocked"])
    p.add_argument("--duration-ms", type=int, required=True)
    p.add_argument("--blocked-reason", default=None)

    # clear - clear meta state
    subparsers.add_parser("clear", help="Clear meta state")

    args = parser.parse_args()

    if args.command == "health":
        meta = OrchestratorMeta.load(args.objective)
        print(json.dumps(meta.get_health_report(), indent=2))

    elif args.command == "warnings":
        meta = OrchestratorMeta.load(args.objective)
        warning = meta.get_active_warnings()
        print(json.dumps({"warning": warning}))

    elif args.command == "complete":
        meta = OrchestratorMeta.load(args.objective)
        action = meta.on_task_complete(
            task_id=args.task_id,
            status=args.status,
            duration_ms=args.duration_ms,
            blocked_reason=args.blocked_reason
        )
        print(json.dumps({
            "action": action,
            "retry_count": meta.get_retry_count(args.task_id),
            "should_abort": meta.should_abort()
        }, indent=2))

    elif args.command == "clear":
        cleared = OrchestratorMeta.clear()
        print(json.dumps({"cleared": cleared}))



if __name__ == "__main__":
    _cli()
