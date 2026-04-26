"""Dev container management — targets Bachelor VPS at 5.181.177.113."""

import subprocess

BACHELOR_HOST = "5.181.177.113"
SSH_KEY = "/root/.hermes/bachelor/bachelor_ed25519"
CONTAINER = "pop_dev"
WORKSPACES = {
    "pop": "/workspace/pop",
    "bachelor_party": "/workspace/bachelor_party",
    "dreamwave-fm": "/workspace/dreamwave-fm",
}


def ssh(cmd: str) -> str:
    """Run a command on the bachelor VPS via SSH."""
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
         f"root@{BACHELOR_HOST}", cmd],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr


def cmd_status(args) -> str:
    """Check if dev container is running."""
    out = ssh(f"docker inspect -f '{{{{.State.Running}}}}' {CONTAINER} 2>&1")
    if "true" in out:
        return f"[OK] Container {CONTAINER} is running"
    return f"[DOWN] Container {CONTAINER} not running"


def cmd_start(args) -> str:
    """Start the dev container (idempotent)."""
    check = ssh(f"docker inspect -f '{{{{.State.Running}}}}' {CONTAINER} 2>&1")
    if "true" in check:
        return f"Container {CONTAINER} already running"

    # Try to start existing stopped container
    start = ssh(f"docker start {CONTAINER} 2>&1")
    if "started" in start.lower() or start == "":
        return f"[OK] Container {CONTAINER} started"

    # Container doesn't exist — create it
    mounts = " ".join(
        f"-v {src}:{dst}" for dst, src in WORKSPACES.items()
    )
    create = ssh(
        f"docker run -d --name {CONTAINER} --restart unless-stopped {mounts} "
        f"-w /workspace/pop python:3.13-slim sleep infinity 2>&1"
    )
    if CONTAINER in create or "sha256:" in create:
        # Install git and pip in the container
        ssh(f"docker exec {CONTAINER} apt-get update -qq")
        ssh(f"docker exec {CONTAINER} apt-get install -y -qq git python3-pip")
        ssh(f"docker exec {CONTAINER} pip install --quiet pytest pytest-mock")
        return f"[OK] Container {CONTAINER} created and started"
    return f"[FAIL] Could not start container:\n{create}"


def cmd_stop(args) -> str:
    """Stop the dev container."""
    stop = ssh(f"docker stop {CONTAINER} 2>&1")
    if CONTAINER in stop or stop == "":
        return f"[OK] Container {CONTAINER} stopped"
    return f"[FAIL] Could not stop:\n{stop}"


def cmd_restart(args) -> str:
    """Restart the dev container."""
    stop = cmd_stop(args)
    start = cmd_start(args)
    return f"{stop}\n{start}"


def cmd_exec(args) -> str:
    """Run a command inside the dev container.

    Usage: pop dev exec [--workspace WS] -- <command>
    Defaults to /workspace/pop if --workspace not specified.
    """
    workspace = getattr(args, "workspace", None) or "/workspace/pop"
    if workspace not in WORKSPACES.values():
        return f"[FAIL] Unknown workspace: {workspace}"

    cmd_str = " ".join(args.command)
    out = ssh(f"docker exec -w {workspace} {CONTAINER} {cmd_str}")
    return out


def cmd_shell(args) -> str:
    """Drop into a shell inside the dev container."""
    ssh(f"docker exec -it {CONTAINER} /bin/bash")
    return ""


def cmd_ps(args) -> str:
    """List running processes inside the container."""
    return ssh(f"docker exec {CONTAINER} ps aux 2>&1 | head -30")


def cmd_logs(args) -> str:
    """Tail container logs."""
    return ssh(f"docker logs --tail {getattr(args, 'lines', 30)} {CONTAINER} 2>&1")


def cmd_workspace(args) -> str:
    """List mounted workspaces."""
    lines = ["Mounted workspaces:", ""]
    for name, path in WORKSPACES.items():
        out = ssh(f"docker exec {CONTAINER} ls {path} 2>&1 | head -3")
        status = "OK" if "LICENSE" in out or "README" in out or "setup" in out else out.strip()[:50]
        lines.append(f"  {name}: {path}  [{status}]")
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

    p_exec = sub.add_parser("exec", help="Run command inside container")
    p_exec.set_defaults(fn=cmd_exec)
    p_exec.add_argument("--workspace", "-w", dest="workspace",
                        choices=list(WORKSPACES.values()),
                        help="Workspace path (default: /workspace/pop)")
    p_exec.add_argument("command", nargs="+", help="Command to run")

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
