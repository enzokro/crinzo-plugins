"""Test FTL phase state machine."""

import json
import sys
from pathlib import Path

import pytest


class TestPhaseTransitions:
    """Test phase transition logic."""

    def test_initial_state_is_none(self, phase_module):
        """Initial phase state should be 'none'."""
        state = phase_module.get_state()
        assert state["phase"] == "none"
        assert state["started_at"] is None
        assert state["transitions"] == []

    def test_valid_transition_none_to_explore(self, phase_module):
        """Can transition from none to explore."""
        assert phase_module.can_transition("none", "explore") is True
        state = phase_module.transition("explore")
        assert state["phase"] == "explore"
        assert state["started_at"] is not None
        assert len(state["transitions"]) == 1
        assert state["transitions"][0]["from"] == "none"
        assert state["transitions"][0]["to"] == "explore"

    def test_invalid_transition_none_to_build(self, phase_module):
        """Cannot transition directly from none to build."""
        assert phase_module.can_transition("none", "build") is False
        with pytest.raises(ValueError) as exc_info:
            phase_module.transition("build")
        assert "Invalid transition" in str(exc_info.value)
        assert "none -> build" in str(exc_info.value)

    def test_valid_transition_chain(self, phase_module):
        """Test full valid transition chain through all phases."""
        # none -> explore
        phase_module.transition("explore")
        assert phase_module.get_state()["phase"] == "explore"

        # explore -> plan
        phase_module.transition("plan")
        assert phase_module.get_state()["phase"] == "plan"

        # plan -> build
        phase_module.transition("build")
        assert phase_module.get_state()["phase"] == "build"

        # build -> observe
        phase_module.transition("observe")
        assert phase_module.get_state()["phase"] == "observe"

        # observe -> complete
        phase_module.transition("complete")
        state = phase_module.get_state()
        assert state["phase"] == "complete"
        assert len(state["transitions"]) == 5

    def test_can_loop_in_build(self, phase_module):
        """Build can transition to itself for iterative work."""
        phase_module.transition("explore")
        phase_module.transition("plan")
        phase_module.transition("build")

        # build -> build is valid
        assert phase_module.can_transition("build", "build") is True
        phase_module.transition("build")
        assert phase_module.get_state()["phase"] == "build"

    def test_plan_can_return_to_explore(self, phase_module):
        """Plan can transition back to explore for re-exploration."""
        phase_module.transition("explore")
        phase_module.transition("plan")

        # plan -> explore is valid
        assert phase_module.can_transition("plan", "explore") is True
        phase_module.transition("explore")
        assert phase_module.get_state()["phase"] == "explore"

    def test_error_state_from_explore(self, phase_module):
        """Can transition to error from explore."""
        phase_module.transition("explore")
        assert phase_module.can_transition("explore", "error") is True
        phase_module.transition("error")
        assert phase_module.get_state()["phase"] == "error"

    def test_error_state_from_plan(self, phase_module):
        """Can transition to error from plan."""
        phase_module.transition("explore")
        phase_module.transition("plan")
        assert phase_module.can_transition("plan", "error") is True
        phase_module.transition("error")
        assert phase_module.get_state()["phase"] == "error"

    def test_error_state_from_build(self, phase_module):
        """Can transition to error from build."""
        phase_module.transition("explore")
        phase_module.transition("plan")
        phase_module.transition("build")
        assert phase_module.can_transition("build", "error") is True
        phase_module.transition("error")
        assert phase_module.get_state()["phase"] == "error"

    def test_error_recovery_to_explore(self, phase_module):
        """Can recover from error to explore."""
        phase_module.transition("explore")
        phase_module.transition("error")

        # error -> explore is valid (retry)
        assert phase_module.can_transition("error", "explore") is True
        phase_module.transition("explore")
        assert phase_module.get_state()["phase"] == "explore"

    def test_error_abort_to_complete(self, phase_module):
        """Can abort from error to complete."""
        phase_module.transition("explore")
        phase_module.transition("error")

        # error -> complete is valid (abort)
        assert phase_module.can_transition("error", "complete") is True
        phase_module.transition("complete")
        assert phase_module.get_state()["phase"] == "complete"

    def test_reset_clears_state(self, phase_module):
        """Reset returns to initial state."""
        phase_module.transition("explore")
        phase_module.transition("plan")

        state = phase_module.reset()
        assert state["phase"] == "none"
        assert state["started_at"] is None
        assert state["transitions"] == []

    def test_transitions_recorded_in_order(self, phase_module):
        """Transitions are recorded with timestamps."""
        phase_module.transition("explore")
        phase_module.transition("plan")
        phase_module.transition("build")

        state = phase_module.get_state()
        transitions = state["transitions"]

        assert len(transitions) == 3
        assert transitions[0]["from"] == "none"
        assert transitions[0]["to"] == "explore"
        assert transitions[1]["from"] == "explore"
        assert transitions[1]["to"] == "plan"
        assert transitions[2]["from"] == "plan"
        assert transitions[2]["to"] == "build"

        # Each transition has a timestamp
        for t in transitions:
            assert "at" in t


class TestCanTransitionMatrix:
    """Test the full transition matrix."""

    @pytest.mark.parametrize("from_phase,to_phase,expected", [
        # From none
        ("none", "explore", True),
        ("none", "plan", False),
        ("none", "build", False),
        ("none", "observe", False),
        ("none", "complete", False),
        ("none", "error", False),

        # From explore
        ("explore", "none", False),
        ("explore", "plan", True),
        ("explore", "build", False),
        ("explore", "observe", False),
        ("explore", "complete", False),
        ("explore", "error", True),

        # From plan
        ("plan", "none", False),
        ("plan", "explore", True),  # Re-explore
        ("plan", "build", True),
        ("plan", "observe", False),
        ("plan", "complete", False),
        ("plan", "error", True),

        # From build
        ("build", "none", False),
        ("build", "explore", False),
        ("build", "plan", False),
        ("build", "build", True),  # Self-loop
        ("build", "observe", True),
        ("build", "complete", False),
        ("build", "error", True),

        # From observe
        ("observe", "none", False),
        ("observe", "explore", False),
        ("observe", "plan", False),
        ("observe", "build", False),
        ("observe", "complete", True),
        ("observe", "error", True),

        # From complete
        ("complete", "none", True),  # Restart
        ("complete", "explore", False),
        ("complete", "plan", False),
        ("complete", "build", False),
        ("complete", "observe", False),
        ("complete", "error", False),

        # From error
        ("error", "none", False),
        ("error", "explore", True),  # Retry
        ("error", "plan", False),
        ("error", "build", False),
        ("error", "observe", False),
        ("error", "complete", True),  # Abort
    ])
    def test_transition_validity(self, phase_module, from_phase, to_phase, expected):
        """Test all phase transitions against expected validity."""
        assert phase_module.can_transition(from_phase, to_phase) is expected


class TestTriggerError:
    """Test trigger_error() helper function."""

    def test_trigger_error_from_explore(self, phase_module):
        """trigger_error transitions from explore to error."""
        phase_module.transition("explore")
        result = phase_module.trigger_error("timeout", "Explorer timed out")

        assert result["phase"] == "error"
        assert result["error_type"] == "timeout"
        assert result["error_message"] == "Explorer timed out"

    def test_trigger_error_from_complete(self, phase_module):
        """trigger_error from complete doesn't transition."""
        phase_module.transition("explore")
        phase_module.transition("plan")
        phase_module.transition("build")
        phase_module.transition("observe")
        phase_module.transition("complete")

        result = phase_module.trigger_error("test", "Should not transition")

        assert result["phase"] == "complete"
        assert result["transition_attempted"] is False
        assert "Cannot transition from complete" in result["reason"]

    def test_trigger_error_from_error(self, phase_module):
        """trigger_error when already in error doesn't re-trigger."""
        phase_module.transition("explore")
        phase_module.transition("error")

        result = phase_module.trigger_error("second_error", "Already in error")

        assert result["phase"] == "error"
        assert result["transition_attempted"] is False


class TestErrorBoundary:
    """Test error_boundary context manager."""

    def test_error_boundary_on_exception(self, phase_module):
        """error_boundary transitions to error on exception."""
        phase_module.transition("explore")

        with pytest.raises(ValueError):
            with phase_module.error_boundary("test_operation"):
                raise ValueError("Test error")

        assert phase_module.get_state()["phase"] == "error"

    def test_error_boundary_no_exception(self, phase_module):
        """error_boundary doesn't change state without exception."""
        phase_module.transition("explore")

        with phase_module.error_boundary("safe_operation"):
            pass  # No error

        assert phase_module.get_state()["phase"] == "explore"


class TestGetDuration:
    """Test get_duration() function."""

    def test_duration_before_start(self, phase_module):
        """Duration is None before workflow starts."""
        assert phase_module.get_duration() is None

    def test_duration_after_start(self, phase_module):
        """Duration is positive after workflow starts."""
        phase_module.transition("explore")
        import time
        time.sleep(0.01)  # Small delay

        duration = phase_module.get_duration()
        assert duration is not None
        assert duration >= 0.01
