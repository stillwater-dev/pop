"""Tests for dev.py — dev container management on Bachelor VPS."""

from argparse import Namespace
from unittest.mock import patch

import pytest

from pop import cli, dev


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_args(**kwargs):
    defaults = dict(command=[], workspace=None, lines=30)
    defaults.update(kwargs)
    return Namespace(**defaults)


# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------

def test_container_running_ignores_known_host_warning():
    result = type(
        "Result",
        (),
        {
            "returncode": 0,
            "stdout": "true\n",
            "stderr": "Warning: Permanently added '5.181.177.113' (ED25519) to the list of known hosts.\n",
        },
    )()
    with patch("subprocess.run", return_value=result):
        assert dev._container_running() is True


def test_ssh_argv_keeps_accept_new_and_forces_tty_when_requested():
    argv = dev._ssh_argv("echo hi", tty=True)
    assert "StrictHostKeyChecking=accept-new" in argv
    assert "-tt" in argv


# ---------------------------------------------------------------------------
# cmd_start
# ---------------------------------------------------------------------------

def test_start_creates_container_with_correct_mounts():
    calls = []

    def fake_ssh(cmd):
        calls.append(cmd)
        if cmd.startswith("docker inspect -f"):
            return "Error: No such object: pop_dev"
        if cmd.startswith("docker run -d"):
            return "sha256:abc123"
        if cmd.startswith("docker exec pop_dev apt-get update -qq"):
            return "__HERMES_EXIT__0"
        if cmd.startswith("docker exec pop_dev apt-get install -y -qq git python3-pip procps"):
            return "__HERMES_EXIT__0"
        if cmd.startswith("docker exec pop_dev python3 -m pip install --quiet pytest pytest-mock"):
            return "__HERMES_EXIT__0"
        raise AssertionError(f"Unexpected command: {cmd}")

    def fake_ssh_result(cmd):
        if cmd.startswith("docker inspect -f '{{.State.Running}}'"):
            return 1, "Error: No such object: pop_dev"
        return 0, "1"

    with patch.object(dev, "ssh", side_effect=fake_ssh), patch.object(dev, "ssh_result", side_effect=fake_ssh_result):
        result = dev.cmd_start(make_args())

    create_cmd = next(cmd for cmd in calls if cmd.startswith("docker run -d"))
    assert "-v /root/pop:/workspace/pop" in create_cmd
    assert "-v /root/bachelor_party:/workspace/bachelor_party" in create_cmd
    assert "-v /root/dreamwave-fm:/workspace/dreamwave-fm" in create_cmd
    assert "[OK]" in result


# ---------------------------------------------------------------------------
# cmd_exec
# ---------------------------------------------------------------------------

def test_exec_accepts_workspace_alias_name():
    calls = []

    def fake_ssh_result(cmd):
        calls.append(cmd)
        return 0, "ok"

    with patch.object(dev, "ssh_result", side_effect=fake_ssh_result):
        result = dev.cmd_exec(make_args(workspace="bachelor_party", command=["pwd"]))

    assert result == dev.CommandResult("ok", 0)
    assert calls == ["docker exec -w /workspace/bachelor_party pop_dev pwd"]


def test_exec_rejects_unknown_workspace_alias():
    result = dev.cmd_exec(make_args(workspace="nope", command=["pwd"]))
    assert result == dev.CommandResult("[FAIL] Unknown workspace: nope", 2)


def test_exec_strips_leading_separator_for_flagged_commands():
    calls = []

    def fake_ssh_result(cmd):
        calls.append(cmd)
        return 0, "ok"

    with patch.object(dev, "ssh_result", side_effect=fake_ssh_result):
        result = dev.cmd_exec(make_args(workspace="pop", command=["--", "ls", "-la"]))

    assert result == dev.CommandResult("ok", 0)
    assert calls == ["docker exec -w /workspace/pop pop_dev ls -la"]


def test_exec_fails_when_no_command_provided():
    result = dev.cmd_exec(make_args(command=[]))
    assert result == dev.CommandResult("[FAIL] No command provided. Usage: pop dev exec [--workspace WS] [--] <command>", 2)


def test_exec_returns_nonzero_exit_code_and_default_failure_message_when_silent():
    with patch.object(dev, "ssh_result", return_value=(7, "")):
        result = dev.cmd_exec(make_args(command=["false"]))

    assert result == dev.CommandResult("[FAIL] Command exited with status 7", 7)


def test_logs_rejects_missing_container():
    with patch.object(dev, "_container_exists", return_value=False):
        result = dev.cmd_logs(make_args())

    assert result == "[FAIL] Container pop_dev does not exist"


def test_ps_rejects_missing_container():
    with patch.object(dev, "_container_exists", return_value=False):
        result = dev.cmd_ps(make_args())

    assert result == "[FAIL] Container pop_dev does not exist"


def test_ps_surfaces_missing_ps_binary_as_fail():
    with patch.object(dev, "_container_exists", return_value=True), \
         patch.object(dev, "ssh_result", return_value=(0, "ps missing -- run pop dev doctor --fix")):
        result = dev.cmd_ps(make_args())

    assert result == "[FAIL] ps missing -- run pop dev doctor --fix"


def test_status_surfaces_container_probe_failures():
    with patch.object(dev, "_container_exists", side_effect=RuntimeError("ssh handshake failed")):
        result = dev.cmd_status(make_args())

    assert result == "[FAIL] Could not inspect container existence:\nssh handshake failed"


def test_shell_returns_command_result_exit_code():
    with patch.object(dev, "ssh_interactive", return_value=255) as mocked:
        result = dev.cmd_shell(make_args())

    mocked.assert_called_once_with("docker exec -it pop_dev /bin/bash")
    assert result == dev.CommandResult("[FAIL] Interactive shell exited with status 255", 255)


def test_stop_rejects_missing_container():
    with patch.object(dev, "_container_exists", return_value=False):
        result = dev.cmd_stop(make_args())

    assert result == "[FAIL] Container pop_dev does not exist"


def test_stop_surfaces_container_probe_failures():
    with patch.object(dev, "_container_exists", side_effect=RuntimeError("ssh handshake failed")):
        result = dev.cmd_stop(make_args())

    assert result == "[FAIL] Could not inspect container existence:\nssh handshake failed"


# ---------------------------------------------------------------------------
# cmd_bootstrap
# ---------------------------------------------------------------------------

def test_bootstrap_refreshes_running_container_and_returns_doctor_summary():
    calls = []

    def fake_ssh(cmd):
        calls.append(cmd)
        if cmd.startswith("docker inspect -f '{{.State.Running}}'"):
            return "true"
        if cmd.startswith("docker exec pop_dev apt-get update -qq"):
            return "__HERMES_EXIT__0"
        if cmd.startswith("docker exec pop_dev apt-get install -y -qq git python3-pip procps"):
            return "__HERMES_EXIT__0"
        if cmd.startswith("docker exec pop_dev python3 -m pip install --quiet pytest pytest-mock"):
            return "__HERMES_EXIT__0"
        if cmd.startswith("docker inspect -f '{{.Config.Image}}'"):
            return "python:3.13-slim"
        if cmd.startswith("docker inspect -f '{{.HostConfig.RestartPolicy.Name}}'"):
            return "unless-stopped"
        if "test -d /workspace/pop" in cmd:
            return "OK /workspace/pop"
        if "test -d /workspace/bachelor_party" in cmd:
            return "OK /workspace/bachelor_party"
        if "test -d /workspace/dreamwave-fm" in cmd:
            return "OK /workspace/dreamwave-fm"
        if "command -v git" in cmd:
            return "__HERMES_EXIT__0"
        if "command -v pip" in cmd:
            return "__HERMES_EXIT__0"
        if "command -v ps" in cmd:
            return "__HERMES_EXIT__0"
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch.object(dev, "ssh", side_effect=fake_ssh):
        result = dev.cmd_bootstrap(make_args())

    assert "[OK] Container pop_dev already running; bootstrap refreshed" in result
    assert "Container: pop_dev [RUNNING]" in result
    assert any(cmd.startswith("docker exec pop_dev apt-get update -qq") for cmd in calls)
    assert any(cmd.startswith("docker exec pop_dev python3 -m pip install --quiet pytest pytest-mock") for cmd in calls)


# ---------------------------------------------------------------------------
# cmd_workspace
# ---------------------------------------------------------------------------

def test_workspace_marks_existing_directory_ok():
    def fake_ssh(cmd):
        if "test -d /workspace/pop" in cmd:
            return "OK /workspace/pop"
        if "test -d /workspace/bachelor_party" in cmd:
            return "OK /workspace/bachelor_party"
        if "test -d /workspace/dreamwave-fm" in cmd:
            return "OK /workspace/dreamwave-fm"
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch.object(dev, "ssh", side_effect=fake_ssh):
        result = dev.cmd_workspace(make_args())

    assert "pop: /workspace/pop  [OK]" in result
    assert "bachelor_party: /workspace/bachelor_party  [OK]" in result
    assert "dreamwave-fm: /workspace/dreamwave-fm  [OK]" in result


# ---------------------------------------------------------------------------
# cmd_doctor
# ---------------------------------------------------------------------------

def test_doctor_reports_container_health_and_missing_tools():
    def fake_ssh(cmd):
        if cmd.startswith("docker inspect -f '{{.State.Running}}'"):
            return "true"
        if cmd.startswith("docker inspect -f '{{.Config.Image}}'"):
            return "python:3.13-slim"
        if cmd.startswith("docker inspect -f '{{.HostConfig.RestartPolicy.Name}}'"):
            return "unless-stopped"
        if "test -d /workspace/pop" in cmd:
            return "OK /workspace/pop"
        if "test -d /workspace/bachelor_party" in cmd:
            return "OK /workspace/bachelor_party"
        if "test -d /workspace/dreamwave-fm" in cmd:
            return "OK /workspace/dreamwave-fm"
        if "command -v git" in cmd:
            return "__HERMES_EXIT__0"
        if "command -v pip" in cmd:
            return "__HERMES_EXIT__1"
        if "command -v ps" in cmd:
            return "__HERMES_EXIT__1"
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch.object(dev, "_container_exists", return_value=True), patch.object(dev, "ssh", side_effect=fake_ssh):
        result = dev.cmd_doctor(make_args())

    assert "Container: pop_dev [RUNNING]" in result
    assert "Image: python:3.13-slim" in result
    assert "Restart policy: unless-stopped" in result
    assert "git: OK" in result
    assert "pip: MISSING" in result
    assert "ps: MISSING" in result
    assert "bachelor_party: OK" in result


def test_doctor_marks_tools_missing_on_docker_exec_error():
    def fake_ssh(cmd):
        if cmd.startswith("docker inspect -f '{{.Config.Image}}'"):
            return "python:3.13-slim"
        if cmd.startswith("docker inspect -f '{{.HostConfig.RestartPolicy.Name}}'"):
            return "unless-stopped"
        if "test -d /workspace/pop" in cmd:
            return "Error response from daemon: container is not running"
        if "test -d /workspace/bachelor_party" in cmd:
            return "Error response from daemon: container is not running"
        if "test -d /workspace/dreamwave-fm" in cmd:
            return "Error response from daemon: container is not running"
        if "command -v git" in cmd:
            return "__HERMES_EXIT__127Error response from daemon: container is not running"
        if "command -v pip" in cmd:
            return "__HERMES_EXIT__127Error response from daemon: container is not running"
        if "command -v ps" in cmd:
            return "__HERMES_EXIT__127Error response from daemon: container is not running"
        raise AssertionError(f"Unexpected command: {cmd}")

    def fake_ssh_result(cmd):
        if cmd.startswith("docker inspect -f '{{.State.Running}}'"):
            return 0, "false"
        return 0, ""

    with patch.object(dev, "_container_exists", return_value=True), \
         patch.object(dev, "ssh", side_effect=fake_ssh), \
         patch.object(dev, "ssh_result", side_effect=fake_ssh_result):
        result = dev.cmd_doctor(make_args())

    assert "Container: pop_dev [DOWN]" in result
    assert "git: MISSING" in result
    assert "pip: MISSING" in result
    assert "ps: MISSING" in result


# ---------------------------------------------------------------------------
# cmd_info
# ---------------------------------------------------------------------------

def test_info_summarizes_container_details():
    def fake_ssh(cmd):
        if cmd.startswith("docker inspect -f '{{.State.Running}}'"):
            return "true"
        if cmd.startswith("docker inspect -f '{{.Config.Image}}'"):
            return "python:3.13-slim"
        if cmd.startswith("docker inspect -f '{{.HostConfig.RestartPolicy.Name}}'"):
            return "unless-stopped"
        if cmd.startswith("docker inspect -f '{{range .Mounts}}"):
            return (
                "/root/pop -> /workspace/pop\n"
                "/root/bachelor_party -> /workspace/bachelor_party\n"
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch.object(dev, "_container_exists", return_value=True), patch.object(dev, "ssh", side_effect=fake_ssh):
        result = dev.cmd_info(make_args())

    assert "Name: pop_dev" in result
    assert "Status: running" in result
    assert "Image: python:3.13-slim" in result
    assert "Restart: unless-stopped" in result
    assert "/root/pop -> /workspace/pop" in result


def test_info_reports_missing_container_cleanly():
    with patch.object(dev, "_container_exists", return_value=False):
        result = dev.cmd_info(make_args())

    assert "Status: missing" in result
    assert "Image: (container missing)" in result
    assert "Mounts:\n(container missing)" in result


def test_info_reports_probe_failure_cleanly():
    with patch.object(dev, "_container_exists", side_effect=RuntimeError("ssh handshake failed")):
        result = dev.cmd_info(make_args())

    assert "Status: unknown" in result
    assert "Image: (ssh probe failed)" in result
    assert "Mounts:\nssh handshake failed" in result


def test_doctor_reports_missing_container_cleanly():
    def fake_ssh(cmd):
        if cmd.startswith("docker inspect -f '{{.Config.Image}}'"):
            return "Error: No such object: pop_dev"
        if cmd.startswith("docker inspect -f '{{.HostConfig.RestartPolicy.Name}}'"):
            return "Error: No such object: pop_dev"
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch.object(dev, "_container_exists", return_value=False), patch.object(dev, "_container_running", return_value=False), patch.object(dev, "_workspace_ok", return_value=False), patch.object(dev, "_command_ok", return_value=False), patch.object(dev, "ssh", side_effect=fake_ssh):
        result = dev.cmd_doctor(make_args())

    assert "Container: pop_dev [MISSING]" in result
    assert "Image: (container missing)" in result
    assert "Restart policy: (container missing)" in result


def test_doctor_fails_early_on_ssh_probe_error():
    """Doctor returns [FAIL] immediately when container probe fails, without calling _container_running."""
    with patch.object(dev, "_container_exists", side_effect=RuntimeError("SSH probe failed with exit 255")), \
         patch.object(dev, "_container_running") as mock_running:
        result = dev.cmd_doctor(make_args())

    assert result.startswith("[FAIL] Could not inspect container existence:")
    assert "SSH probe failed with exit 255" in result
    mock_running.assert_not_called()


def test_cli_uses_command_result_exit_code(monkeypatch):
    printed = []

    monkeypatch.setattr(cli.dev, "cmd_exec", lambda args: dev.CommandResult("boom", 7))
    monkeypatch.setattr(cli.console, "print", lambda message: printed.append(str(message)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "dev", "exec", "false"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 7
    assert printed == ["boom"]


def test_cli_treats_fail_string_as_exit_one(monkeypatch):
    printed = []

    monkeypatch.setattr(cli.dev, "cmd_stop", lambda args: "[FAIL] Container pop_dev does not exist")
    monkeypatch.setattr(cli.console, "print", lambda message: printed.append(str(message)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "dev", "stop"])

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 1
    assert printed == ["[FAIL] Container pop_dev does not exist"]


def test_cli_treats_dreamwave_missing_repo_as_exit_one(monkeypatch):
    printed = []

    monkeypatch.setattr(cli.console, "print", lambda message: printed.append(str(message)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "dreamwave", "deploy", "/nope"])

    with patch("subprocess.run", return_value=type("Result", (), {"returncode": 1, "stdout": "", "stderr": ""})()):
        with pytest.raises(SystemExit) as exc:
            cli.main()

    assert exc.value.code == 1
    assert printed == ["[FAIL] Local repo directory not found: /nope"]


def test_cli_treats_bachelor_health_failure_as_exit_one(monkeypatch):
    printed = []

    monkeypatch.setattr(cli.console, "print", lambda message: printed.append(str(message)))
    monkeypatch.setattr(cli.sys, "argv", ["pop", "bachelor", "health"])

    with patch("urllib.request.urlopen", side_effect=Exception("Connection refused")):
        with pytest.raises(SystemExit) as exc:
            cli.main()

    assert exc.value.code == 1
    assert printed == ["[FAIL] Connection refused"]
