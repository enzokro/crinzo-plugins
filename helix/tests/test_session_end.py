"""Tests for session_end hook - cleanup and maintenance."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "lib" / "hooks"))


class TestSessionEndCleanup:
    """Tests for session_end main() cleanup actions."""

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
        mock_prune = MagicMock(return_value={"pruned": 0, "orphans_cleaned": 0})
        mock_memory_core = MagicMock(decay=mock_decay, prune=mock_prune)

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch.dict("sys.modules", {"memory.core": mock_memory_core}), \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        # Verify decay was actually called
        mock_decay.assert_called_once()

        # Verify log reflects decay count
        log_file = helix_dir / "session.log"
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "SESSION_END" in log_content
        assert "decayed=3" in log_content

    def test_session_end_runs_prune(self, tmp_path):
        """session_end calls prune() after decay()."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()

        mock_decay = MagicMock(return_value={"decayed": 0})
        mock_prune = MagicMock(return_value={"pruned": 2, "orphans_cleaned": 1})
        mock_memory_core = MagicMock(decay=mock_decay, prune=mock_prune)

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch.dict("sys.modules", {"memory.core": mock_memory_core}), \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        # Verify prune was called
        mock_prune.assert_called_once()

        # Verify log reflects prune count
        log_file = helix_dir / "session.log"
        log_content = log_file.read_text()
        assert "pruned=2" in log_content
        assert "orphans=1" in log_content

    def test_session_end_cleans_sideband_files(self, tmp_path):
        """session_end removes stale sideband files from .helix/injected/."""
        helix_dir = tmp_path / ".helix"
        helix_dir.mkdir()
        injected_dir = helix_dir / "injected"
        injected_dir.mkdir()

        # Create stale sideband files (from crashed agents)
        (injected_dir / "agent-orphan-1.json").write_text('{"names": ["a"]}')
        (injected_dir / "agent-orphan-2.json").write_text('{"names": ["b"]}')

        with patch("hooks.session_end.get_helix_dir", return_value=helix_dir), \
             patch("hooks.session_end.sys") as mock_sys, \
             patch("builtins.print"):
            mock_sys.stdin.read.return_value = "{}"
            from hooks.session_end import main
            main()

        # Files should be cleaned up
        assert list(injected_dir.iterdir()) == []
