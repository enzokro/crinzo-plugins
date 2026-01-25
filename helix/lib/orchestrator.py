#!/usr/bin/env python3
"""State Machine Orchestrator for Helix.

Replaces the pseudo-code in SKILL.md with explicit state transitions.
The state machine provides:
- Explicit transition guards (validation before state change)
- Checkpoints at significant states (for recovery)
- Clear error states with typed reasons
- Recovery paths from STALLED state

State Diagram:
    INIT -> EXPLORING -> EXPLORED -> PLANNING -> PLANNED -> BUILDING -> BUILT -> OBSERVING -> DONE
                                                    |
                                                    v
                                                 STALLED -> (PLANNING | BUILT | ERROR)
                                                    |
    Any state -------------------------------------> ERROR

The SKILL.md becomes documentation of this state machine, not the implementation.
Agents are spawned at appropriate states, their output triggers transitions.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class State(Enum):
    """Orchestrator states."""
    INIT = auto()
    EXPLORING = auto()
    EXPLORED = auto()
    PLANNING = auto()
    PLANNED = auto()
    BUILDING = auto()
    STALLED = auto()
    BUILT = auto()
    OBSERVING = auto()
    DONE = auto()
    ERROR = auto()


class ErrorReason(Enum):
    """Typed error reasons for ERROR state."""
    EMPTY_EXPLORATION = "empty_exploration"
    NO_TASKS = "no_tasks"
    CYCLES_DETECTED = "cycles_detected"
    ALL_BLOCKED = "all_blocked"
    VELOCITY_COLLAPSE = "velocity_collapse"
    SYSTEMIC_FAILURE = "systemic_failure"
    INVALID_TRANSITION = "invalid_transition"
    USER_ABORT = "user_abort"


@dataclass
class Checkpoint:
    """Serializable checkpoint at a state boundary."""
    state: str  # State.name
    data: Dict[str, Any]
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class TransitionResult:
    """Result of a state transition attempt."""
    success: bool
    from_state: State
    to_state: State
    data: Optional[Dict[str, Any]] = None
    error_reason: Optional[ErrorReason] = None
    error_context: Optional[Dict[str, Any]] = None


class Orchestrator:
    """Explicit state machine orchestrator for Helix.

    Usage:
        orch = Orchestrator(objective="Add user authentication")

        # Start exploration
        orch.transition("start")  # INIT -> EXPLORING

        # After explorer completes
        exploration_data = {...}
        result = orch.transition("exploration_complete", exploration_data)
        if result.to_state == State.ERROR:
            handle_error(result.error_reason)

        # Continue through states...
    """

    def __init__(self, objective: str):
        """Initialize orchestrator for an objective.

        Args:
            objective: The user's goal
        """
        self.objective = objective
        self.state = State.INIT
        self.checkpoints: Dict[State, Checkpoint] = {}
        self.error_context: Optional[Dict[str, Any]] = None

        # Phase data
        self.exploration_result: Optional[Dict[str, Any]] = None
        self.task_ids: List[str] = []
        self.task_mapping: Dict[str, str] = {}  # seq -> task_id
        self.dependencies: Dict[str, List[str]] = {}  # task_id -> blocker_ids

        # Build phase tracking
        self.completed_tasks: List[str] = []
        self.blocked_tasks: List[str] = []

    def transition(
        self,
        event: str,
        data: Optional[Dict[str, Any]] = None
    ) -> TransitionResult:
        """Execute a state transition.

        Args:
            event: The event triggering transition
            data: Optional data associated with the event

        Returns:
            TransitionResult with success/failure and new state
        """
        data = data or {}

        # Define valid transitions: (current_state, event) -> handler
        transitions = {
            (State.INIT, "start"): self._to_exploring,
            (State.EXPLORING, "exploration_complete"): self._to_explored,
            (State.EXPLORED, "start_planning"): self._to_planning,
            (State.PLANNING, "tasks_created"): self._to_planned,
            (State.PLANNING, "clarify_needed"): self._stay_planning,
            (State.PLANNED, "start_building"): self._to_building,
            (State.BUILDING, "task_complete"): self._task_complete,
            (State.BUILDING, "all_complete"): self._to_built,
            (State.BUILDING, "stalled"): self._to_stalled,
            (State.STALLED, "replan"): self._stalled_to_planning,
            (State.STALLED, "skip"): self._stalled_to_built,
            (State.STALLED, "abort"): self._to_error,
            (State.BUILT, "start_observing"): self._to_observing,
            (State.OBSERVING, "observation_complete"): self._to_done,
        }

        key = (self.state, event)
        if key not in transitions:
            return TransitionResult(
                success=False,
                from_state=self.state,
                to_state=State.ERROR,
                error_reason=ErrorReason.INVALID_TRANSITION,
                error_context={"current_state": self.state.name, "event": event}
            )

        handler = transitions[key]
        return handler(data)

    def _to_exploring(self, data: Dict) -> TransitionResult:
        """INIT -> EXPLORING: Always succeeds."""
        from_state = self.state
        self.state = State.EXPLORING
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state
        )

    def _to_explored(self, data: Dict) -> TransitionResult:
        """EXPLORING -> EXPLORED: Guard - must have targets."""
        from_state = self.state

        # Guard: exploration must have targets
        targets = data.get("targets", {})
        files = targets.get("files", [])

        if not files:
            self.state = State.ERROR
            self.error_context = {"reason": "empty_exploration", "data": data}
            return TransitionResult(
                success=False,
                from_state=from_state,
                to_state=State.ERROR,
                error_reason=ErrorReason.EMPTY_EXPLORATION,
                error_context=data
            )

        self.exploration_result = data
        self.state = State.EXPLORED
        self._checkpoint(State.EXPLORED, data)

        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _to_planning(self, data: Dict) -> TransitionResult:
        """EXPLORED -> PLANNING: Always succeeds."""
        from_state = self.state
        self.state = State.PLANNING
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state
        )

    def _stay_planning(self, data: Dict) -> TransitionResult:
        """PLANNING -> PLANNING: Clarification loop."""
        return TransitionResult(
            success=True,
            from_state=State.PLANNING,
            to_state=State.PLANNING,
            data={"questions": data.get("questions", [])}
        )

    def _to_planned(self, data: Dict) -> TransitionResult:
        """PLANNING -> PLANNED: Guard - must have tasks, no cycles."""
        from_state = self.state

        task_ids = data.get("task_ids", [])
        if not task_ids:
            self.state = State.ERROR
            return TransitionResult(
                success=False,
                from_state=from_state,
                to_state=State.ERROR,
                error_reason=ErrorReason.NO_TASKS,
                error_context=data
            )

        # Check for cycles
        dependencies = data.get("dependencies", {})
        cycles = self._detect_cycles(dependencies)
        if cycles:
            self.state = State.ERROR
            return TransitionResult(
                success=False,
                from_state=from_state,
                to_state=State.ERROR,
                error_reason=ErrorReason.CYCLES_DETECTED,
                error_context={"cycles": cycles}
            )

        self.task_ids = task_ids
        self.task_mapping = data.get("task_mapping", {})
        self.dependencies = dependencies
        self.state = State.PLANNED
        self._checkpoint(State.PLANNED, data)

        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _to_building(self, data: Dict) -> TransitionResult:
        """PLANNED -> BUILDING: Always succeeds."""
        from_state = self.state
        self.state = State.BUILDING
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state
        )

    def _task_complete(self, data: Dict) -> TransitionResult:
        """BUILDING -> BUILDING: Task completion loop."""
        task_id = data.get("task_id")
        status = data.get("status", "delivered")

        if task_id:
            if status == "blocked":
                self.blocked_tasks.append(task_id)
            else:
                self.completed_tasks.append(task_id)

        return TransitionResult(
            success=True,
            from_state=State.BUILDING,
            to_state=State.BUILDING,
            data=data
        )

    def _to_built(self, data: Dict) -> TransitionResult:
        """BUILDING -> BUILT: All tasks complete."""
        from_state = self.state
        self.state = State.BUILT
        self._checkpoint(State.BUILT, {
            "completed": self.completed_tasks,
            "blocked": self.blocked_tasks
        })
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _to_stalled(self, data: Dict) -> TransitionResult:
        """BUILDING -> STALLED: No ready tasks but pending exist."""
        from_state = self.state
        self.state = State.STALLED
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _stalled_to_planning(self, data: Dict) -> TransitionResult:
        """STALLED -> PLANNING: User chose to replan."""
        from_state = self.state
        self.state = State.PLANNING
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _stalled_to_built(self, data: Dict) -> TransitionResult:
        """STALLED -> BUILT: User chose to skip blocked tasks."""
        from_state = self.state
        self.state = State.BUILT
        self._checkpoint(State.BUILT, {
            "completed": self.completed_tasks,
            "blocked": self.blocked_tasks,
            "skipped": data.get("skipped", [])
        })
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _to_observing(self, data: Dict) -> TransitionResult:
        """BUILT -> OBSERVING: Always succeeds."""
        from_state = self.state
        self.state = State.OBSERVING
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state
        )

    def _to_done(self, data: Dict) -> TransitionResult:
        """OBSERVING -> DONE: Always succeeds."""
        from_state = self.state
        self.state = State.DONE
        return TransitionResult(
            success=True,
            from_state=from_state,
            to_state=self.state,
            data=data
        )

    def _to_error(self, data: Dict) -> TransitionResult:
        """Any -> ERROR: Explicit error transition."""
        from_state = self.state
        self.state = State.ERROR
        self.error_context = data

        reason = ErrorReason.USER_ABORT
        if "reason" in data:
            try:
                reason = ErrorReason(data["reason"])
            except ValueError:
                pass

        return TransitionResult(
            success=False,
            from_state=from_state,
            to_state=State.ERROR,
            error_reason=reason,
            error_context=data
        )

    def _checkpoint(self, state: State, data: Dict[str, Any]) -> None:
        """Save checkpoint to disk for recovery."""
        cp = Checkpoint(state=state.name, data=data)
        self.checkpoints[state] = cp

        # Persist to disk
        cp_dir = Path.cwd() / ".helix" / "checkpoints"
        cp_dir.mkdir(parents=True, exist_ok=True)

        cp_path = cp_dir / f"{state.name.lower()}.json"
        cp_path.write_text(json.dumps({
            "state": state.name,
            "objective": self.objective,
            "data": data,
            "timestamp": cp.timestamp
        }, indent=2))

    def _detect_cycles(self, dependencies: Dict[str, List[str]]) -> List[List[str]]:
        """Detect cycles in dependency graph using DFS."""
        cycles = []
        visited = set()
        rec_stack = set()

        def dfs(node: str, path: List[str]) -> None:
            if node in rec_stack:
                try:
                    cycle_start = path.index(node)
                    cycle = path[cycle_start:] + [node]
                    cycles.append(cycle)
                except ValueError:
                    pass
                return

            if node in visited:
                return

            visited.add(node)
            rec_stack.add(node)

            for neighbor in dependencies.get(node, []):
                dfs(neighbor, path + [node])

            rec_stack.discard(node)

        for node in dependencies:
            if node not in visited:
                dfs(node, [])

        return cycles

    def get_ready_tasks(self, all_tasks: List[Dict]) -> List[str]:
        """Get task IDs that are ready to execute.

        A task is ready if:
        - status == "pending"
        - all blockedBy tasks are completed (not blocked)

        Args:
            all_tasks: List of task data from TaskList

        Returns:
            List of task IDs ready for execution
        """
        ready = []
        completed_ids = set(self.completed_tasks)
        blocked_ids = set(self.blocked_tasks)

        for task in all_tasks:
            if task.get("status") != "pending":
                continue

            blockers = task.get("blockedBy", [])
            all_blockers_done = all(
                b in completed_ids and b not in blocked_ids
                for b in blockers
            )

            if all_blockers_done:
                ready.append(task.get("id"))

        return ready

    def check_stalled(self, all_tasks: List[Dict]) -> Tuple[bool, Optional[Dict]]:
        """Check if build is stalled.

        Stalled = pending tasks exist but none are ready
        (all are blocked by BLOCKED tasks)

        Args:
            all_tasks: List of task data from TaskList

        Returns:
            (is_stalled, stall_info)
        """
        pending = [t for t in all_tasks if t.get("status") == "pending"]
        if not pending:
            return False, None

        ready = self.get_ready_tasks(all_tasks)
        if ready:
            return False, None

        # Stalled - analyze why
        blocked_by_blocked = []
        for task in pending:
            blockers = task.get("blockedBy", [])
            blocked_blockers = [b for b in blockers if b in self.blocked_tasks]
            if blocked_blockers:
                blocked_by_blocked.append({
                    "task_id": task.get("id"),
                    "subject": task.get("subject"),
                    "blocked_by": blocked_blockers
                })

        return True, {
            "pending_count": len(pending),
            "blocked_by_blocked": blocked_by_blocked
        }

    def get_state(self) -> Dict[str, Any]:
        """Get current orchestrator state for inspection."""
        return {
            "state": self.state.name,
            "objective": self.objective,
            "task_ids": self.task_ids,
            "completed": self.completed_tasks,
            "blocked": self.blocked_tasks,
            "has_exploration": self.exploration_result is not None,
            "checkpoints": list(self.checkpoints.keys())
        }

    @classmethod
    def resume(cls, objective: str) -> "Orchestrator":
        """Resume orchestrator from checkpoints.

        Loads the most recent checkpoint and restores state.

        Args:
            objective: The objective to resume

        Returns:
            Orchestrator instance at last checkpoint state
        """
        orch = cls(objective)
        cp_dir = Path.cwd() / ".helix" / "checkpoints"

        if not cp_dir.exists():
            return orch

        # Load checkpoints in order
        state_order = [State.EXPLORED, State.PLANNED, State.BUILT]
        for state in state_order:
            cp_path = cp_dir / f"{state.name.lower()}.json"
            if cp_path.exists():
                try:
                    data = json.loads(cp_path.read_text())
                    if data.get("objective") == objective:
                        orch.checkpoints[state] = Checkpoint(
                            state=state.name,
                            data=data.get("data", {}),
                            timestamp=data.get("timestamp", "")
                        )
                        orch.state = state

                        # Restore data from checkpoint
                        if state == State.EXPLORED:
                            orch.exploration_result = data.get("data", {})
                        elif state == State.PLANNED:
                            orch.task_ids = data.get("data", {}).get("task_ids", [])
                            orch.task_mapping = data.get("data", {}).get("task_mapping", {})
                            orch.dependencies = data.get("data", {}).get("dependencies", {})
                        elif state == State.BUILT:
                            orch.completed_tasks = data.get("data", {}).get("completed", [])
                            orch.blocked_tasks = data.get("data", {}).get("blocked", [])
                except Exception:
                    pass

        return orch


def clear_checkpoints() -> int:
    """Clear all checkpoints (for starting fresh).

    Returns:
        Number of checkpoints cleared
    """
    cp_dir = Path.cwd() / ".helix" / "checkpoints"
    if not cp_dir.exists():
        return 0

    count = 0
    for cp_file in cp_dir.glob("*.json"):
        cp_file.unlink()
        count += 1

    return count


# CLI for testing and inspection
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Helix orchestrator state machine")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    # status command
    p = subparsers.add_parser("status", help="Show current orchestrator state")
    p.add_argument("--objective", required=True, help="The objective")

    # clear command
    subparsers.add_parser("clear", help="Clear all checkpoints")

    # transitions command
    subparsers.add_parser("transitions", help="List valid transitions")

    args = parser.parse_args()

    if args.cmd == "status":
        orch = Orchestrator.resume(args.objective)
        print(json.dumps(orch.get_state(), indent=2))

    elif args.cmd == "clear":
        count = clear_checkpoints()
        print(json.dumps({"cleared": count}))

    elif args.cmd == "transitions":
        transitions = [
            "INIT -> EXPLORING (event: start)",
            "EXPLORING -> EXPLORED (event: exploration_complete, guard: targets.files not empty)",
            "EXPLORED -> PLANNING (event: start_planning)",
            "PLANNING -> PLANNED (event: tasks_created, guard: task_ids not empty, no cycles)",
            "PLANNING -> PLANNING (event: clarify_needed, loop for questions)",
            "PLANNED -> BUILDING (event: start_building)",
            "BUILDING -> BUILDING (event: task_complete, loop for each task)",
            "BUILDING -> BUILT (event: all_complete)",
            "BUILDING -> STALLED (event: stalled, when no ready tasks)",
            "STALLED -> PLANNING (event: replan)",
            "STALLED -> BUILT (event: skip)",
            "STALLED -> ERROR (event: abort)",
            "BUILT -> OBSERVING (event: start_observing)",
            "OBSERVING -> DONE (event: observation_complete)",
        ]
        for t in transitions:
            print(t)
