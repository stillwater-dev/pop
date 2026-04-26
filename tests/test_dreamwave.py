"""Tests for dreamwave.py — DREAMWAVE FM VPS management."""

from argparse import Namespace
from unittest.mock import MagicMock, patch

from pop import dreamwave


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(**kwargs):
    defaults = dict(local="/root/vaporwave-radio", dry_run=False, lines=30, limit=20, command="pwd")
    defaults.update(kwargs)
    return Namespace(**defaults)


def run_result(returncode=0, stdout="", stderr=""):
    result = MagicMock()
    result.returncode = returncode
    result.stdout = stdout
    result.stderr = stderr
    return result


# ---------------------------------------------------------------------------
# cmd_deploy_tracks
# ---------------------------------------------------------------------------

def test_deploy_tracks_uses_batch_safe_rsync_transport():
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["ls", "/root/vaporwave-radio/tracks"]:
            return run_result(returncode=0)
        if kwargs.get("shell") and cmd == ["ls", "/root/vaporwave-radio/tracks/*.mp3"]:
            return run_result(returncode=0, stdout="a.mp3\nb.mp3\n")
        if cmd[0] == "rsync":
            return run_result(returncode=0, stdout="sent 10 bytes\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        result = dreamwave.cmd_deploy_tracks(make_args(local="/root/vaporwave-radio/tracks"))

    rsync_cmd = next(cmd for cmd in calls if cmd[0] == "rsync")
    assert rsync_cmd[rsync_cmd.index("-e") + 1] == dreamwave.RSYNC_SSH
    assert "Deployed 2 tracks." in result


def test_tracks_reports_failure_when_listing_fails():
    with patch.object(dreamwave, "ssh", return_value=""):
        result = dreamwave.cmd_tracks(make_args())

    assert result == "[FAIL] Could not list tracks"


def test_status_prefixes_ssh_failure():
    with patch.object(dreamwave, "ssh", return_value="Permission denied (publickey)."):
        result = dreamwave.cmd_status(make_args())

    assert result.startswith("[FAIL]")
    assert "Permission denied" in result


def test_restart_prefixes_remote_failure():
    with patch.object(dreamwave, "ssh", return_value="Job for dreamwave-backend.service failed because the control process exited with error code."):
        result = dreamwave.cmd_restart(make_args())

    assert result.startswith("[FAIL]")
    assert "dreamwave-backend.service failed" in result


def test_logs_prefixes_remote_query_failure():
    with patch.object(dreamwave, "ssh", return_value="Unit dreamwave-backend.service could not be found."):
        result = dreamwave.cmd_logs(make_args())

    assert result.startswith("[FAIL]")
    assert "could not be found" in result


def test_logs_preserve_benign_not_found_log_lines():
    line = "2026-04-25T12:00:00 api cache not found for key user:123"
    with patch.object(dreamwave, "ssh", return_value=line):
        result = dreamwave.cmd_logs(make_args())

    assert result == line


def test_tracks_prefixes_remote_query_failure():
    with patch.object(dreamwave, "ssh", return_value="ls: cannot access '/var/www/dreamwave/tracks/*.mp3': No such file or directory"):
        result = dreamwave.cmd_tracks(make_args())

    assert result.startswith("[FAIL]")
    assert "cannot access" in result


# ---------------------------------------------------------------------------
# cmd_deploy
# ---------------------------------------------------------------------------

def test_deploy_missing_local_repo():
    with patch("subprocess.run", return_value=run_result(returncode=1)):
        result = dreamwave.cmd_deploy(make_args(local="/nope"))

    assert "[FAIL] Local repo directory not found: /nope" == result


def test_deploy_dry_run_skips_reload_and_remote_mutation():
    calls = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        if cmd[0] == "rsync":
            return run_result(stdout="sending incremental file list\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    ssh_calls = []

    def fake_ssh(host, cmd, capture=True):
        ssh_calls.append((host, cmd, capture))
        if cmd == f"test -d {dreamwave.DREAMWAVE_PATH}; printf '__HERMES_EXIT__%s' $?":
            return "__HERMES_EXIT__0"
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            result = dreamwave.cmd_deploy(make_args(dry_run=True))

    rsync_cmd = next(cmd for cmd in calls if cmd[0] == "rsync")
    assert "--dry-run" in rsync_cmd
    assert rsync_cmd[rsync_cmd.index("-e") + 1] == dreamwave.RSYNC_SSH
    assert "[DRY RUN] DREAMWAVE deploy preview" in result
    assert ssh_calls == [
        (dreamwave.DREAMWAVE_HOST, f"test -d {dreamwave.DREAMWAVE_PATH}; printf '__HERMES_EXIT__%s' $?", True)
    ]


def test_deploy_dry_run_fails_when_remote_path_missing():
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    def fake_ssh(host, cmd, capture=True):
        if cmd == f"test -d {dreamwave.DREAMWAVE_PATH}; printf '__HERMES_EXIT__%s' $?":
            return "__HERMES_EXIT__1"
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            result = dreamwave.cmd_deploy(make_args(dry_run=True))

    assert "[FAIL] DREAMWAVE path missing on VPS for dry-run preview" in result


def test_deploy_dry_run_surfaces_ssh_failure():
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    def fake_ssh(host, cmd, capture=True):
        if cmd == f"test -d {dreamwave.DREAMWAVE_PATH}; printf '__HERMES_EXIT__%s' $?":
            return "Permission denied (publickey)."
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            result = dreamwave.cmd_deploy(make_args(dry_run=True))

    assert "[FAIL] Could not verify DREAMWAVE path on VPS" in result


def test_deploy_success_reloads_and_checks_frontend():
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        if cmd[0] == "rsync":
            return run_result(stdout="sending incremental file list\nindex.html\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    ssh_calls = []

    def fake_ssh(host, cmd, capture=True):
        ssh_calls.append(cmd)
        if cmd == f"mkdir -p {dreamwave.DREAMWAVE_PATH}":
            return ""
        if cmd == "nginx -t && systemctl reload nginx":
            return "nginx reloaded"
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    response = MagicMock()
    response.status = 200

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            with patch("urllib.request.urlopen", return_value=response):
                result = dreamwave.cmd_deploy(make_args())

    assert "[OK] Deployed DREAMWAVE frontend" in result
    assert "Frontend OK: HTTP 200" in result
    assert "nginx reloaded" in result
    assert ssh_calls == [
        f"mkdir -p {dreamwave.DREAMWAVE_PATH}",
        "nginx -t && systemctl reload nginx",
    ]


def test_deploy_reload_failure_returns_fail():
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        if cmd[0] == "rsync":
            return run_result(stdout="sending incremental file list\nindex.html\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    def fake_ssh(host, cmd, capture=True):
        if cmd == f"mkdir -p {dreamwave.DREAMWAVE_PATH}":
            return ""
        if cmd == "nginx -t && systemctl reload nginx":
            return "nginx: configuration file test failed"
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    response = MagicMock()
    response.status = 200

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            with patch("urllib.request.urlopen", return_value=response):
                result = dreamwave.cmd_deploy(make_args())

    assert "[FAIL]" in result
    assert "nginx" in result.lower()



def test_deploy_frontend_check_failure_returns_fail():
    def fake_run(cmd, *args, **kwargs):
        if cmd[:2] == ["test", "-d"]:
            return run_result(returncode=0)
        if cmd[0] == "rsync":
            return run_result(stdout="sending incremental file list\nindex.html\n")
        raise AssertionError(f"Unexpected subprocess call: {cmd}")

    def fake_ssh(host, cmd, capture=True):
        if cmd == f"mkdir -p {dreamwave.DREAMWAVE_PATH}":
            return ""
        if cmd == "nginx -t && systemctl reload nginx":
            return "nginx reloaded"
        raise AssertionError(f"Unexpected ssh call: {cmd}")

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(dreamwave, "ssh", side_effect=fake_ssh):
            with patch("urllib.request.urlopen", side_effect=Exception("timeout")):
                result = dreamwave.cmd_deploy(make_args())

    assert "[FAIL]" in result
    assert "frontend check failed" in result.lower()
