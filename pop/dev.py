"""Dev container management — targets Bachelor VPS at 5.181.177.113."""

import argparse
import shlex
import subprocess
from dataclasses import dataclass

BACHELOR_HOST = "5.181.177.113"
SSH_KEY = "/root/.hermes/bachelor/bachelor_ed25519"
CONTAINER = "pop_dev"
WORKSPACES = {
    "pop": "/workspace/pop",
    "bachelor_party": "/workspace/bachelor_party",
    "dreamwave-fm": "/workspace/dreamwave-fm",
}
REQUIRED_COMMANDS = ("git", "pip", "ps")


@dataclass
class CommandResult:
    output: str = ""
    exit_code: int = 0


def _strip_ssh_noise(text: str) -> str:
    lines = [
        line
        for line in (text or "").splitlines()
        if "Permanently added" not in line
    ]
    return "\n".join(lines)


def _ssh_argv(cmd: str, tty: bool = False) -> list[str]:
    argv = [
        "ssh",
        "-i",
        SSH_KEY,
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
    ]
    if tty:
        argv.append("-tt")
    argv.extend([f"root@{BACHELOR_HOST}", cmd])
    return argv


def _combine_ssh_output(stdout: str | None, stderr: str | None) -> str:
    stdout = _strip_ssh_noise(stdout or "")
    stderr = _strip_ssh_noise(stderr or "")
    if stdout and stderr:
        return f"{stdout}\n{stderr}"
    return stdout or stderr


def ssh(cmd: str) -> str:
    """Run a command on the bachelor VPS via SSH and return combined output."""
    _, output = ssh_result(cmd)
    return output


def ssh_result(cmd: str) -> tuple[int, str]:
    """Run a command on the bachelor VPS via SSH and return exit code + output."""
    result = subprocess.run(_ssh_argv(cmd), capture_output=True, text=True)
    return result.returncode, _combine_ssh_output(result.stdout, result.stderr)


def ssh_interactive(cmd: str) -> int:
    """Run an interactive SSH command, inheriting the local terminal."""
    result = subprocess.run(_ssh_argv(cmd, tty=True), text=True)
    return result.returncode


def _clean(out: str) -> str:
    return (out or "").strip()


def _exit_code(out: str, marker: str = "__HERMES_EXIT__") -> int | None:
    text = out or ""
    idx = text.find(marker)
    if idx == -1:
        return None
    digits = []
    for ch in text[idx + len(marker):]:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    return int("".join(digits)) if digits else None


def _container_running() -> bool:
    return _clean(ssh(f"docker inspect -f '{{{{.State.Running}}}}' {CONTAINER} 2>&1")) == "true"


def _container_exists() -> bool:
    exit_code, out = ssh_result(f"docker inspect {CONTAINER} >/dev/null 2>&1; echo $?")
    if exit_code != 0:
        raise RuntimeError(_clean(out) or f"SSH probe failed with exit {exit_code}")

    cleaned = _clean(out)
    if cleaned not in {"0", "1"}:
        raise RuntimeError(cleaned or "unexpected empty response from docker inspect probe")
    return cleaned == "0"


def _resolve_workspace(value: str | None) -> str | None:
    if not value:
        return WORKSPACES["pop"]
    if value in WORKSPACES:
        return WORKSPACES[value]
    if value in WORKSPACES.values():
        return value
    return None


def _workspace_ok(path: str) -> bool:
    out = ssh(f"docker exec {CONTAINER} sh -lc 'test -d {path} && echo OK {path}'")
    return _clean(out) == f"OK {path}"


def _command_ok(command: str) -> bool:
    marker = "__HERMES_EXIT__"
    out = ssh(
        f"docker exec {CONTAINER} sh -lc 'command -v {shlex.quote(command)} >/dev/null 2>&1'; "
        f"printf '{marker}%s' $?"
    )
    return _exit_code(out, marker) == 0


def _bootstrap_container() -> tuple[bool, list[str]]:
    marker = "__HERMES_EXIT__"
    failures = []
    steps = [
        ("apt-get update", f"docker exec {CONTAINER} apt-get update -qq"),
        ("apt-get install", f"docker exec {CONTAINER} apt-get install -y -qq git python3-pip procps"),
        ("pip install", f"docker exec {CONTAINER} python3 -m pip install --quiet pytest pytest-mock"),
    ]
    for label, command in steps:
        out = ssh(f"{command}; printf '{marker}%s' $?")
        if _exit_code(out, marker) != 0:
            failures.append(f"{label}: {_clean(out)}")
    return (not failures, failures)


def cmd_status(args) -> str:
    """Check if dev container is running."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"
    if not exists:
        return f"[DOWN] Container {CONTAINER} does not exist"
    if _container_running():
        return f"[OK] Container {CONTAINER} is running"
    return f"[DOWN] Container {CONTAINER} not running"


def cmd_start(args) -> str:
    """Start the dev container (idempotent)."""
    if _container_running():
        return f"Container {CONTAINER} already running"

    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"

    if exists:
        start = ssh(f"docker start {CONTAINER} 2>&1")
        if "started" in start.lower() or _clean(start) == CONTAINER:
            ok, failures = _bootstrap_container()
            if not ok:
                return f"[FAIL] Container {CONTAINER} started but bootstrap failed:\n" + "\n".join(failures)
            return f"[OK] Container {CONTAINER} started"
        return f"[FAIL] Could not start existing container:\n{start}"

    # Container doesn't exist — create it.
    mounts = " ".join(
        f"-v /root/{name}:{path}" for name, path in WORKSPACES.items()
    )
    create = ssh(
        f"docker run -d --name {CONTAINER} --restart unless-stopped {mounts} "
        f"-w /workspace/pop python:3.13-slim sleep infinity 2>&1"
    )
    if CONTAINER in create or "sha256:" in create:
        ok, failures = _bootstrap_container()
        if not ok:
            return f"[FAIL] Container {CONTAINER} created but bootstrap failed:\n" + "\n".join(failures)
        return f"[OK] Container {CONTAINER} created and started"
    return f"[FAIL] Could not start container:\n{create}"


def cmd_stop(args) -> str:
    """Stop the dev container."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"

    if not exists:
        return f"[FAIL] Container {CONTAINER} does not exist"
    if not _container_running():
        return f"[DOWN] Container {CONTAINER} already stopped"

    stop = ssh(f"docker stop {CONTAINER} 2>&1")
    if _clean(stop) == CONTAINER or stop == "":
        return f"[OK] Container {CONTAINER} stopped"
    return f"[FAIL] Could not stop:\n{stop}"


def cmd_restart(args) -> str:
    """Restart the dev container."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"

    if not exists:
        return cmd_start(args)

    stop = cmd_stop(args)
    if stop.startswith("[FAIL]"):
        return stop
    start = cmd_start(args)
    return f"{stop}\n{start}"


def cmd_recreate(args) -> str:
    """Recreate the dev container from scratch."""
    ssh(f"docker rm -f {CONTAINER} 2>&1")
    return cmd_start(args)


def cmd_bootstrap(args) -> str:
    """Ensure the dev container is running and bootstrapped with required tools."""
    if _container_running():
        ok, failures = _bootstrap_container()
        if not ok:
            return "[FAIL] Container pop_dev is running but bootstrap failed:\n" + "\n".join(failures)
        prefix = f"[OK] Container {CONTAINER} already running; bootstrap refreshed"
    else:
        prefix = cmd_start(args)
        if "[FAIL]" in prefix:
            return prefix
    return f"{prefix}\n\n{cmd_doctor(args)}"


def cmd_exec(args) -> CommandResult:
    """Run a command inside the dev container.

    Usage: pop dev exec [--workspace WS] [--] <command>
    Use `--` when the inner command has its own flags, e.g.:
      pop dev exec --workspace pop -- ls -la
    Defaults to /workspace/pop if --workspace not specified.
    """
    workspace = _resolve_workspace(getattr(args, "workspace", None))
    if not workspace:
        return CommandResult(f"[FAIL] Unknown workspace: {getattr(args, 'workspace', None)}", 2)

    command = list(getattr(args, "command", []) or [])
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return CommandResult("[FAIL] No command provided. Usage: pop dev exec [--workspace WS] [--] <command>", 2)

    cmd_str = " ".join(shlex.quote(part) for part in command)
    exit_code, out = ssh_result(f"docker exec -w {workspace} {CONTAINER} {cmd_str}")
    if exit_code != 0 and not _clean(out):
        out = f"[FAIL] Command exited with status {exit_code}"
    return CommandResult(out, exit_code)


def cmd_shell(args) -> CommandResult:
    """Drop into a shell inside the dev container."""
    exit_code = ssh_interactive(f"docker exec -it {CONTAINER} /bin/bash")
    if exit_code == 0:
        return CommandResult()
    return CommandResult(f"[FAIL] Interactive shell exited with status {exit_code}", exit_code)


def cmd_ps(args) -> str:
    """List running processes inside the container."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"
    if not exists:
        return f"[FAIL] Container {CONTAINER} does not exist"
    out = ssh(
        f"docker exec {CONTAINER} sh -lc 'if command -v ps >/dev/null 2>&1; "
        f"then ps aux; else echo ps missing -- run pop dev doctor --fix; fi'"
    )
    cleaned = _clean(out)
    if cleaned.startswith("ps missing --"):
        return f"[FAIL] {cleaned}"
    return out


def cmd_logs(args) -> str:
    """Tail container logs."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return f"[FAIL] Could not inspect container existence:\n{exc}"
    if not exists:
        return f"[FAIL] Container {CONTAINER} does not exist"
    return ssh(f"docker logs --tail {getattr(args, 'lines', 30)} {CONTAINER} 2>&1")


def cmd_workspace(args) -> str:
    """List mounted workspaces."""
    lines = ["Mounted workspaces:", ""]
    for name, path in WORKSPACES.items():
        status = "OK" if _workspace_ok(path) else "MISSING"
        lines.append(f"  {name}: {path}  [{status}]")
    return "\n".join(lines)


def cmd_info(args) -> str:
    """Show container summary info."""
    try:
        exists = _container_exists()
    except RuntimeError as exc:
        return (
            f"Name: {CONTAINER}\n"
            f"Status: unknown\n"
            f"Image: (ssh probe failed)\n"
            f"Restart: (ssh probe failed)\n"
            f"Mounts:\n{exc}"
        )

    if not exists:
        return (
            f"Name: {CONTAINER}\n"
            f"Status: missing\n"
            f"Image: (container missing)\n"
            f"Restart: (container missing)\n"
            f"Mounts:\n(container missing)"
        )

    running = _clean(ssh(f"docker inspect -f '{{{{.State.Running}}}}' {CONTAINER} 2>&1"))
    image = _clean(ssh(f"docker inspect -f '{{{{.Config.Image}}}}' {CONTAINER} 2>&1"))
    restart = _clean(ssh(f"docker inspect -f '{{{{.HostConfig.RestartPolicy.Name}}}}' {CONTAINER} 2>&1"))
    mounts = _clean(
        ssh(
            f"docker inspect -f '{{{{range .Mounts}}}}{{{{.Source}}}} -> {{{{.Destination}}}}{{{{println}}}}{{{{end}}}}' {CONTAINER} 2>&1"
        )
    )
    status = "running" if running == "true" else "stopped"
    return (
        f"Name: {CONTAINER}\n"
        f"Status: {status}\n"
        f"Image: {image}\n"
        f"Restart: {restart}\n"
        f"Mounts:\n{mounts}"
    )


def cmd_doctor(args) -> str:
    """Check container health, mounts, and required tools."""
    fix = getattr(args, "fix", False)
    if fix:
        if not _container_running():
            start_result = cmd_start(args)
            if "[FAIL]" in start_result:
                return start_result
        else:
            ok, failures = _bootstrap_container()
            if not ok:
                return "[FAIL] Container bootstrap failed during doctor --fix:\n" + "\n".join(failures)

    try:
        exists = _container_exists()
    except RuntimeError as exc:
        exists = None
        inspect_error = str(exc)
    else:
        inspect_error = None

    if exists is False:
        lines = [
            f"Container: {CONTAINER} [MISSING]",
            "Image: (container missing)",
            "Restart policy: (container missing)",
            "",
            "Workspaces:",
        ]
        for name in WORKSPACES:
            lines.append(f"  - {name}: MISSING")
        lines.append("")
        lines.append("Tools:")
        for command in REQUIRED_COMMANDS:
            lines.append(f"  - {command}: MISSING")
        if fix:
            lines.append("")
            lines.append("Applied fixes: skipped because container is missing")
        return "\n".join(lines)

    running = _container_running()
    if inspect_error:
        image = "(ssh probe failed)"
        restart = inspect_error
    else:
        image = _clean(ssh(f"docker inspect -f '{{{{.Config.Image}}}}' {CONTAINER} 2>&1"))
        restart = _clean(ssh(f"docker inspect -f '{{{{.HostConfig.RestartPolicy.Name}}}}' {CONTAINER} 2>&1"))

    lines = [
        f"Container: {CONTAINER} [{'RUNNING' if running else 'DOWN'}]",
        f"Image: {image}",
        f"Restart policy: {restart}",
        "",
        "Workspaces:",
    ]
    for name, path in WORKSPACES.items():
        lines.append(f"  - {name}: {'OK' if _workspace_ok(path) else 'MISSING'}")

    lines.append("")
    lines.append("Tools:")
    for command in REQUIRED_COMMANDS:
        lines.append(f"  - {command}: {'OK' if _command_ok(command) else 'MISSING'}")

    if fix:
        lines.append("")
        lines.append("Applied fixes: apt packages + pytest tooling install attempted")

    return "\n".join(lines)


def register(subparsers):
    """Register dev subcommands."""
    p_dev = subparsers.add_parser("dev", help="Dev Container — 5.181.177.113")

    sub = p_dev.add_subparsers(dest="dev_cmd", required=True)

    p_status = sub.add_parser("status", help="Check if container is running")
    p_status.set_defaults(fn=cmd_status)

    p_start = sub.add_parser("start", help="Start dev container")
    p_start.set_defaults(fn=cmd_start)

    p_stop = sub.add_parser("stop", help="Stop dev container")
    p_stop.set_defaults(fn=cmd_stop)

    p_restart = sub.add_parser("restart", help="Restart dev container")
    p_restart.set_defaults(fn=cmd_restart)

    p_recreate = sub.add_parser("recreate", help="Recreate dev container from scratch")
    p_recreate.set_defaults(fn=cmd_recreate)

    p_bootstrap = sub.add_parser("bootstrap", help="Ensure container is running and tooling is installed")
    p_bootstrap.set_defaults(fn=cmd_bootstrap)

    p_exec = sub.add_parser("exec", help="Run command inside container")
    p_exec.set_defaults(fn=cmd_exec)
    p_exec.add_argument(
        "--workspace",
        "-w",
        dest="workspace",
        help="Workspace alias or path (default: pop / /workspace/pop)",
    )
    p_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to run (use -- before inner flags)")

    p_shell = sub.add_parser("shell", help="Interactive shell in container")
    p_shell.set_defaults(fn=cmd_shell)

    p_ps = sub.add_parser("ps", help="List processes in container")
    p_ps.set_defaults(fn=cmd_ps)

    p_logs = sub.add_parser("logs", help="Container logs")
    p_logs.set_defaults(fn=cmd_logs)
    p_logs.add_argument("-n", "--lines", type=int, default=30, dest="lines",
                        help="Number of lines to tail")

    p_workspace = sub.add_parser("workspace", help="List mounted workspaces")
    p_workspace.set_defaults(fn=cmd_workspace)

    p_info = sub.add_parser("info", help="Show container info and mounts")
    p_info.set_defaults(fn=cmd_info)

    p_doctor = sub.add_parser("doctor", help="Check container health and required tools")
    p_doctor.add_argument("--fix", action="store_true", help="Install missing container tooling")
    p_doctor.set_defaults(fn=cmd_doctor)
