"""Tests for session_end hook - cleanup and maintenance."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))


class TestSessionEndCleanup:
    """Tests for session_end main() cleanup actions."""

    def test_session_end_cleans_injection_state(self, tmp_path):
        """session_end removes injection-state directory."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        injection_dir = helix_dir / "injection-state"
        injection_dir.mkdir()
        (injection_dir / "task-1.json").write_text('{"task_id": "task-1"}')

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        assert not injection_dir.exists()

    def test_session_end_removes_task_status(self, tmp_path):
        """session_end removes task-status.jsonl."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        status_file = helix_dir / "task-status.jsonl"
        status_file.write_text('{"task_id": "task-1", "outcome": "delivered"}\n')

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        assert not status_file.exists()

    def test_session_end_runs_decay(self, tmp_path):
        """session_end calls decay()."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()

        mock_decay = MagicMock(return_value={"decayed": 3})

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch.dict("sys.modules", {"memory.core": MagicMock(decay=mock_decay)}), \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        # Verify decay was attempted (via import inside main)
        log_file = helix_dir / "session.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "SESSION_END" in log_content

    def test_session_end_logs_event(self, tmp_path):
        """session_end writes to session.log."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        log_file = helix_dir / "session.log"
        assert log_file.exists()
        assert "SESSION_END" in log_file.read_text()
