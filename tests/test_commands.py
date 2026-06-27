# tests/test_commands.py
"""Tests for pop.commands module."""

import pytest
from unittest.mock import MagicMock, patch
from pop.commands import load_playbook, run_command, upload_file


class TestLoadPlaybook:
    """Playbook loading tests."""

    def test_load_playbook_returns_dict(self, tmp_path):
        """load_playbook returns parsed playbook dict."""
        playbook_file = tmp_path / "deploy.yaml"
        playbook_file.write_text("""
vars:
  app_dir: /opt/app
steps:
  - name: Create dir
    command: mkdir -p /opt/app
""")
        result = load_playbook(playbook_file)
        assert isinstance(result, dict)
        assert "steps" in result
        assert result["vars"]["app_dir"] == "/opt/app"


class TestRunCommand:
    """Command execution tests."""

    def test_run_command_calls_server_run(self):
        """run_command delegates to server.run()."""
        mock_server = MagicMock()
        mock_server.run.return_value = "output"
        result = run_command(mock_server, "ls -la")
        mock_server.run.assert_called_once_with("ls -la", bg=False)
        assert result == "output"

    def test_run_command_with_bg_flag(self):
        """run_command passes bg flag to server.run()."""
        mock_server = MagicMock()
        run_command(mock_server, "tail -f /var/log/app.log", bg=True)
        mock_server.run.assert_called_once_with("tail -f /var/log/app.log", bg=True)


class TestUploadFile:
    """File upload tests."""

    def test_upload_file_calls_server_upload(self):
        """upload_file delegates to server.upload()."""
        mock_server = MagicMock()
        upload_file(mock_server, "/local/path.txt", "/remote/path.txt")
        mock_server.upload.assert_called_once_with("/local/path.txt", "/remote/path.txt")
