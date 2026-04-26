"""Tests for bachelor.py — Bachelor Party App VPS management."""

import pytest
from unittest.mock import patch, MagicMock
from argparse import Namespace

from pop import bachelor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(**kwargs):
    """Return a Namespace with defaults for all commands."""
    defaults = dict(command=[], dry_run=False, snapshot=None)
    defaults.update(kwargs)
    return Namespace(**defaults)


def ssh_result(out="", returncode=0):
    r = MagicMock()
    r.returncode = returncode
    r.stdout = out
    r.stderr = ""
    return r


# ---------------------------------------------------------------------------
# ssh()
# ---------------------------------------------------------------------------

def test_ssh_combines_stdout_stderr():
    with patch("subprocess.run", return_value=ssh_result("stdout")) as m:
        result = bachelor.ssh("echo hello")
        m.assert_called_once()
        call_args = m.call_args[0][0]
        assert "ssh" in call_args[0]
        assert "root@5.181.177.113" in call_args
        assert "echo hello" in call_args


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------

def test_status_running():
    with patch("subprocess.run", return_value=ssh_result(
        "root  38345  0.0  1.0 104348 20480 ?  Ss  02:00  0:00  /usr/bin/python3 -m http.server 80"
    )):
        result = bachelor.cmd_status(make_args())
        assert "OK" in result
        assert "38345" in result

def test_status_down():
    with patch("subprocess.run", return_value=ssh_result("")):
        result = bachelor.cmd_status(make_args())
        assert "DOWN" in result


# ---------------------------------------------------------------------------
# cmd_start
# ---------------------------------------------------------------------------

def test_start_already_running():
    with patch("subprocess.run", return_value=ssh_result(
        "root  38345  0.0  1.0 104348 20480 ?  Ss  02:00  0:00  /usr/bin/python3 -m http.server 80"
    )):
        result = bachelor.cmd_start(make_args())
        assert "Already running" in result

def test_start_fresh():
    """Test starting when no process is running — mocks ssh() directly."""
    call_count = [0]
    def fake_ssh(cmd):
        call_count[0] += 1
        r = MagicMock()
        r.returncode = 0
        r.stdout = ""
        r.stderr = ""
        # 1st: check if running → not running
        if call_count[0] == 1:
            r.stdout = ""
        # 2nd: pkill
        elif call_count[0] == 2:
            r.stdout = ""
        # 3rd: mkdir
        elif call_count[0] == 3:
            r.stdout = ""
        # 4th: nohup + ps → process found
        elif call_count[0] == 4:
            r.stdout = "root  39107  0.0  1.0  ...  /usr/bin/python3 -m http.server 80"
        return r.stdout + r.stderr

    with patch.object(bachelor, "ssh", side_effect=fake_ssh):
        result = bachelor.cmd_start(make_args())
        assert "OK" in result
        assert "39107" in result
        assert call_count[0] == 4

def test_start_failure():
    with patch("subprocess.run", return_value=ssh_result("")):
        result = bachelor.cmd_start(make_args())
        assert "FAIL" in result


# ---------------------------------------------------------------------------
# cmd_stop
# ---------------------------------------------------------------------------

def test_stop_not_running():
    with patch("subprocess.run", return_value=ssh_result("")):
        result = bachelor.cmd_stop(make_args())
        assert "not running" in result

def test_stop_kills_pid():
    killed = []
    call_count = [0]
    def run_side_effect(cmd, *, capture_output, text):
        call_count[0] += 1
        r = MagicMock()
        r.returncode = 0
        r.stderr = ""

        # SSH cmd is a list: [..., "root@host", "actual shell command"]
        shell_cmd = cmd[-1] if isinstance(cmd, list) else cmd

        if shell_cmd.startswith("ps aux"):
            # First grep: process is running. Second grep: process is gone.
            if call_count[0] == 1:
                r.stdout = "root  38345  0.0  1.0  ...  /usr/bin/python3 -m http.server 80"
            else:
                r.stdout = ""
            return r

        if shell_cmd.startswith("kill"):
            killed.append(shell_cmd.split()[1])
            r.stdout = ""
            return r

        r.stdout = ""
        return r

    with patch("subprocess.run", side_effect=run_side_effect):
        with patch("time.sleep"):
            result = bachelor.cmd_stop(make_args())
    assert killed[0] == "38345"
    assert "OK" in result


# ---------------------------------------------------------------------------
# cmd_restart
# ---------------------------------------------------------------------------

def test_restart_calls_stop_then_start():
    with patch.object(bachelor, "cmd_stop", return_value="[OK] Stopped") as mock_stop:
        with patch.object(bachelor, "cmd_start", return_value="[OK] Started") as mock_start:
            result = bachelor.cmd_restart(make_args())
            mock_stop.assert_called_once()
            mock_start.assert_called_once()
            assert "Stopped" in result
            assert "Started" in result


# ---------------------------------------------------------------------------
# cmd_health
# ---------------------------------------------------------------------------

def test_health_ok():
    with patch("urllib.request.urlopen") as m:
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"<title>Test App</title>"
        m.return_value = resp
        result = bachelor.cmd_health(make_args())
        assert "OK" in result
        assert "200" in result
        assert "Test App" in result

def test_health_no_title():
    with patch("urllib.request.urlopen") as m:
        resp = MagicMock()
        resp.status = 200
        resp.read.return_value = b"<html></html>"
        m.return_value = resp
        result = bachelor.cmd_health(make_args())
        assert "OK" in result
        assert "(no title)" in result

def test_health_fail():
    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        result = bachelor.cmd_health(make_args())
        assert "FAIL" in result


# ---------------------------------------------------------------------------
# cmd_logs
# ---------------------------------------------------------------------------

def test_logs_returns_tail():
    with patch("subprocess.run", return_value=ssh_result("line1\nline2\nline3")) as m:
        result = bachelor.cmd_logs(make_args())
        assert "line1" in result
        # Should have called mkdir and then tail
        assert m.call_count >= 1


# ---------------------------------------------------------------------------
# cmd_exec
# ---------------------------------------------------------------------------

def test_exec_runs_in_app_dir():
    with patch("subprocess.run", return_value=ssh_result("pwd output")) as m:
        result = bachelor.cmd_exec(make_args(command=["pwd"]))
        call_cmd_list = m.call_args[0][0]
        call_cmd_str = " ".join(call_cmd_list)
        assert "cd /root/bachelor_party" in call_cmd_str
        assert "pwd" in call_cmd_str

def test_exec_joins_multiword_command():
    with patch("subprocess.run", return_value=ssh_result("")) as m:
        bachelor.cmd_exec(make_args(command=["find", ".", "-name", "*.js"]))
        call_cmd_str = " ".join(m.call_args[0][0])
        assert "find" in call_cmd_str
        assert "-name" in call_cmd_str
        assert "*.js" in call_cmd_str


# ---------------------------------------------------------------------------
# cmd_deploy
# ---------------------------------------------------------------------------

def test_deploy_success_restarts():
    with patch("subprocess.run", return_value=ssh_result("sending incremental file list\napp.js")):
        with patch.object(bachelor, "cmd_restart", return_value="[OK] Restarted") as mock_restart:
            result = bachelor.cmd_deploy(make_args())
    assert "Deployed" in result
    mock_restart.assert_called_once()

def test_deploy_dry_run_no_restart():
    with patch("subprocess.run", return_value=ssh_result("sending incremental")):
        with patch.object(bachelor, "cmd_restart") as mock_restart:
            result = bachelor.cmd_deploy(make_args(dry_run=True))
    assert "DRY RUN" in result
    mock_restart.assert_not_called()

def test_deploy_rsync_failure():
    r = MagicMock()
    r.returncode = 2
    r.stdout = ""
    r.stderr = "rsync error: protocol incompatibility"
    with patch("subprocess.run", return_value=r):
        result = bachelor.cmd_deploy(make_args())
    assert "FAIL" in result
    assert "rsync error" in result


# ---------------------------------------------------------------------------
# cmd_vps_status
# ---------------------------------------------------------------------------

def test_vps_status_returns_all_sections():
    with patch("subprocess.run", return_value=ssh_result("df output\n---\nuptime output\n---\nhttp.server")):
        result = bachelor.cmd_vps_status(make_args())
        assert "df output" in result
        assert "uptime output" in result
        assert "http.server" in result


# ---------------------------------------------------------------------------
# cmd_snapshot
# ---------------------------------------------------------------------------

def test_snapshot_success():
    with patch("subprocess.run") as m:
        m.side_effect = [
            ssh_result(""),  # mkdir
            ssh_result(""),  # tar
            ssh_result("-rw-r--r-- 1 root root 46M Apr 26 02:08 /root/.bachelor_snapshots/snapshot_20260425_160834.tar.gz"),
        ]
        result = bachelor.cmd_snapshot(make_args())
        assert "OK" in result
        assert "snapshot_2026" in result

def test_snapshot_tar_error():
    with patch("subprocess.run", return_value=ssh_result("tar: some error")):
        result = bachelor.cmd_snapshot(make_args())
        assert "FAIL" in result


# ---------------------------------------------------------------------------
# cmd_snapshots
# ---------------------------------------------------------------------------

def test_snapshots_empty():
    with patch("subprocess.run", return_value=ssh_result("")):
        result = bachelor.cmd_snapshots(make_args())
        assert "No snapshots found" in result

def test_snapshots_one():
    with patch("subprocess.run", return_value=ssh_result(
        "-rw-r--r-- 1 root root 46M Apr 26 02:08 /root/.bachelor_snapshots/snapshot_20260425_160834.tar.gz"
    )):
        result = bachelor.cmd_snapshots(make_args())
        assert "snapshot_20260425_160834.tar.gz" in result


# ---------------------------------------------------------------------------
# cmd_rollback
# ---------------------------------------------------------------------------

def test_rollback_no_snapshots():
    with patch("subprocess.run", return_value=ssh_result("")):
        result = bachelor.cmd_rollback(make_args())
        assert "FAIL" in result
        assert "No snapshots found" in result

def test_rollback_specific_found():
    with patch("subprocess.run", return_value=ssh_result("OK")):
        with patch.object(bachelor, "cmd_stop", return_value="[OK] Stopped"):
            with patch.object(bachelor, "cmd_start", return_value="[OK] Started"):
                result = bachelor.cmd_rollback(make_args(snapshot="20260425_160834"))
                assert "OK" in result

def test_rollback_specific_not_found():
    with patch("subprocess.run", return_value=ssh_result("MISSING")):
        result = bachelor.cmd_rollback(make_args(snapshot="nonexistent"))
        assert "FAIL" in result
        assert "not found" in result

def test_rollback_uses_latest():
    with patch("subprocess.run", return_value=ssh_result("/root/.bachelor_snapshots/snapshot_20260425_160834.tar.gz")):
        with patch.object(bachelor, "cmd_stop", return_value="[OK] Stopped"):
            with patch.object(bachelor, "cmd_start", return_value="[OK] Started"):
                result = bachelor.cmd_rollback(make_args())
                assert "OK" in result


# ---------------------------------------------------------------------------
# cmd_pull
# ---------------------------------------------------------------------------

def test_pull_success():
    with patch("subprocess.run", return_value=ssh_result("receiving file list\napp.js")) as m:
        result = bachelor.cmd_pull(make_args())
        assert "OK" in result
        call_args = m.call_args[0][0]
        assert "rsync" in call_args

def test_pull_failure():
    r = MagicMock()
    r.returncode = 2
    r.stdout = ""
    r.stderr = "connection refused"
    with patch("subprocess.run", return_value=r):
        result = bachelor.cmd_pull(make_args())
    assert "FAIL" in result
    assert "connection refused" in result


# ---------------------------------------------------------------------------
# Smoke tests — verify all commands are registered
# ---------------------------------------------------------------------------

def test_all_commands_registered():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    bachelor.register(sub)
    for cmd in ["status", "start", "stop", "restart", "health", "logs",
                "vps-status", "deploy", "snapshot", "snapshots",
                "rollback", "pull"]:
        parser.parse_args(["bachelor", cmd])

def test_exec_requires_command():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    bachelor.register(sub)
    with pytest.raises(SystemExit):
        parser.parse_args(["bachelor", "exec"])
