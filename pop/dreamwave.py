"""DREAMWAVE FM management commands."""

import subprocess
from typing import Optional

# DREAMWAVE VPS defaults
DREAMWAVE_HOST = "38.45.71.55"
DREAMWAVE_USER = "root"
DREAMWAVE_KEY = "/root/.ssh/id_ed25519"
DREAMWAVE_PATH = "/var/www/dreamwave"
DREAMWAVE_PORT = 22
LOCAL_REPO = "/root/vaporwave-radio"
SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=5",
]
RSYNC_SSH = f"ssh -i {DREAMWAVE_KEY} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5"

SSH_FAILURE_MARKERS = (
    "host key verification failed",
    "remote host identification has changed",
    "permission denied",
    "could not resolve hostname",
    "connection refused",
    "connection timed out",
    "no route to host",
    "operation timed out",
    "ssh:",
)
REMOTE_COMMAND_FAILURE_MARKERS = (
    " failed",
    "error",
    "[emerg]",
    "not found",
    "permission denied",
)
LOG_QUERY_FAILURE_MARKERS = SSH_FAILURE_MARKERS + (
    "could not be found",
)
TRACKS_QUERY_FAILURE_MARKERS = SSH_FAILURE_MARKERS + (
    "cannot access",
    "no such file or directory",
    "not found",
)


def _strip_ssh_noise(text: str) -> str:
    lines = [
        line
        for line in (text or "").splitlines()
        if "Permanently added" not in line
    ]
    return "\n".join(lines)


def ssh(host: str, cmd: str, capture: bool = True) -> Optional[str]:
    """Run a command on the DREAMWAVE VPS via SSH."""
    full_cmd = [
        "ssh", "-i", DREAMWAVE_KEY,
        *SSH_OPTIONS,
        f"{DREAMWAVE_USER}@{host}",
        cmd
    ]
    result = subprocess.run(full_cmd, capture_output=capture, text=True)
    if capture:
        stdout = _strip_ssh_noise(result.stdout)
        stderr = _strip_ssh_noise(result.stderr)
        if stdout and stderr:
            return f"{stdout}\n{stderr}"
        return stdout or stderr
    return None


def _looks_like_failure(output: Optional[str], markers: tuple[str, ...]) -> bool:
    if output is None:
        return True
    lowered = output.lower()
    return any(marker in lowered for marker in markers)


def _remote_exit_ok(output: Optional[str], marker: str = "__HERMES_EXIT__") -> bool:
    if output is None:
        return False
    return output.strip().startswith(f"{marker}0")


def _fail_prefix(output: Optional[str], fallback: str) -> str:
    cleaned = _strip_ssh_noise(output or "").strip()
    if not cleaned:
        return fallback
    if cleaned.startswith("[FAIL]"):
        return cleaned
    return f"[FAIL] {cleaned}"


def _result_or_fail(output: Optional[str], *, failure_markers: tuple[str, ...], empty_failure: str | None = None, empty_success: str | None = None) -> str:
    cleaned = _strip_ssh_noise(output or "").strip()
    if not cleaned:
        if empty_failure is not None:
            return empty_failure
        return empty_success or ""
    if _looks_like_failure(cleaned, failure_markers):
        return _fail_prefix(cleaned, empty_failure or "[FAIL] Remote command failed")
    return cleaned


def cmd_status(args) -> str:
    """Check backend and nginx status."""
    out = ssh(DREAMWAVE_HOST, "systemctl status dreamwave-backend --no-pager -l; echo '---'; systemctl status nginx --no-pager -l | head -10")
    return _result_or_fail(
        out,
        failure_markers=SSH_FAILURE_MARKERS + REMOTE_COMMAND_FAILURE_MARKERS,
        empty_failure="[FAIL] Could not connect to DREAMWAVE VPS",
    )


def cmd_restart(args) -> str:
    """Restart the backend service."""
    out = ssh(DREAMWAVE_HOST, "systemctl restart dreamwave-backend && systemctl status dreamwave-backend --no-pager | head -20")
    return _result_or_fail(
        out,
        failure_markers=SSH_FAILURE_MARKERS + REMOTE_COMMAND_FAILURE_MARKERS,
        empty_success="Restart command sent",
    )


def cmd_logs(args) -> str:
    """Tail backend logs."""
    lines = args.lines
    out = ssh(DREAMWAVE_HOST, f"journalctl -u dreamwave-backend --no-pager -n {lines}")
    return _result_or_fail(
        out,
        failure_markers=LOG_QUERY_FAILURE_MARKERS,
        empty_failure="[FAIL] Could not fetch logs",
    )


def cmd_reload(args) -> str:
    """Reload nginx."""
    out = ssh(DREAMWAVE_HOST, "nginx -t && systemctl reload nginx")
    return _result_or_fail(
        out,
        failure_markers=SSH_FAILURE_MARKERS + REMOTE_COMMAND_FAILURE_MARKERS,
        empty_success="Reload command sent",
    )


def cmd_tracks(args) -> str:
    """List tracks on the VPS."""
    out = ssh(DREAMWAVE_HOST, f"ls {DREAMWAVE_PATH}/tracks/*.mp3 | head {args.limit} && echo '---' && ssh {DREAMWAVE_USER}@{DREAMWAVE_HOST} 'ls {DREAMWAVE_PATH}/tracks/*.mp3 | wc -l'")
    return _result_or_fail(
        out,
        failure_markers=TRACKS_QUERY_FAILURE_MARKERS,
        empty_failure="[FAIL] Could not list tracks",
    )


def cmd_deploy_tracks(args) -> str:
    """Deploy new tracks from local /root/vaporwave-radio/tracks/ to VPS."""
    local_tracks = args.local

    # Check local tracks exist
    check = subprocess.run(["ls", local_tracks], capture_output=True)
    if check.returncode != 0:
        return f"[FAIL] Local tracks directory not found: {local_tracks}"

    count = subprocess.run(["ls", f"{local_tracks}/*.mp3"], shell=True, capture_output=True, text=True)
    mp3_count = len([l for l in count.stdout.strip().split("\n") if l.endswith(".mp3")])

    # rsync tracks to VPS
    cmd = [
        "rsync", "-avz", "--progress",
        "-e", RSYNC_SSH,
        f"{local_tracks}/",
        f"{DREAMWAVE_USER}@{DREAMWAVE_HOST}:{DREAMWAVE_PATH}/tracks/"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"[FAIL] Deploy failed: {result.stderr}"
    return f"Deployed {mp3_count} tracks.\n{result.stdout[-500:]}"


def cmd_deploy(args) -> str:
    """Deploy DREAMWAVE frontend files from local repo to VPS via rsync."""
    local_repo = args.local
    dry_run = getattr(args, "dry_run", False)

    check = subprocess.run(["test", "-d", local_repo])
    if check.returncode != 0:
        return f"[FAIL] Local repo directory not found: {local_repo}"

    if dry_run:
        marker = "__HERMES_EXIT__"
        path_check = ssh(DREAMWAVE_HOST, f"test -d {DREAMWAVE_PATH}; printf '{marker}%s' $?")
        if _remote_exit_ok(path_check, marker):
            pass
        elif _looks_like_failure(path_check, SSH_FAILURE_MARKERS):
            return f"[FAIL] Could not verify DREAMWAVE path on VPS:\n{path_check}"
        else:
            return f"[FAIL] DREAMWAVE path missing on VPS for dry-run preview: {DREAMWAVE_PATH}\n{path_check or ''}"
    else:
        mkdir_out = ssh(DREAMWAVE_HOST, f"mkdir -p {DREAMWAVE_PATH}")
        if _looks_like_failure(mkdir_out, SSH_FAILURE_MARKERS) or _looks_like_failure(mkdir_out, ("mkdir:",)):
            return f"[FAIL] Could not prepare DREAMWAVE path:\n{mkdir_out}"

    excludes = [
        "--exclude=.git",
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=*.pyo",
        "--exclude=*.log",
        "--exclude=.pytest_cache",
        "--exclude=.DS_Store",
        "--exclude=.env",
        "--exclude=assets/",
        "--exclude=backend/",
        "--exclude=fallback/",
        "--exclude=migrations/",
        "--exclude=server/",
        "--exclude=tracks/",
    ]

    cmd = [
        "rsync", "-avz",
        "-e", RSYNC_SSH,
    ] + excludes + [
        f"{local_repo}/",
        f"{DREAMWAVE_USER}@{DREAMWAVE_HOST}:{DREAMWAVE_PATH}/"
    ]

    if dry_run:
        cmd.insert(1, "--dry-run")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"[FAIL] Deploy failed:\n{result.stderr[-1000:]}"

    summary = result.stdout[-1500:] if result.stdout else "(no rsync output)"
    if dry_run:
        return f"[DRY RUN] DREAMWAVE deploy preview\n{summary}"

    reload_out = ssh(DREAMWAVE_HOST, "nginx -t && systemctl reload nginx") or ""
    if _looks_like_failure(reload_out, SSH_FAILURE_MARKERS) or _looks_like_failure(reload_out, REMOTE_COMMAND_FAILURE_MARKERS):
        return f"[FAIL] Deploy uploaded files but nginx reload failed\n{summary}\n---\n{reload_out}"

    import urllib.request
    try:
        req = urllib.request.Request(
            "https://dream.lewd.win",
            headers={"User-Agent": "Mozilla/5.0 (Hermes pop deploy check)"},
        )
        resp = urllib.request.urlopen(req, timeout=10)
        frontend = f"Frontend OK: HTTP {resp.status}"
    except Exception as e:
        return f"[FAIL] Deploy uploaded files and reloaded nginx, but frontend check failed: {e}\n{summary}\n---\n{reload_out}"

    return f"[OK] Deployed DREAMWAVE frontend\n{summary}\n---\n{reload_out or 'nginx reload command sent'}\n---\n{frontend}"


def cmd_health(args) -> str:
    """Check API health endpoint."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://{DREAMWAVE_HOST}/api/health", timeout=5)
        return f"API OK: {resp.read().decode()}"
    except Exception as e:
        return f"[FAIL] API health check failed: {e}"


def cmd_exec(args) -> str:
    """Run arbitrary command on DREAMWAVE VPS."""
    out = ssh(DREAMWAVE_HOST, args.command)
    return out or "Command produced no output"


def register(subparsers):
    """Register DREAMWAVE subcommands."""
    p_dw = subparsers.add_parser("dreamwave", help="DREAMWAVE FM management")
    p_dw.set_defaults(fn=lambda a: p_dw.print_help())

    sub = p_dw.add_subparsers(dest="dw_cmd", required=True)

    # status
    p_status = sub.add_parser("status", help="Check backend + nginx status")
    p_status.set_defaults(fn=cmd_status)

    # restart
    p_restart = sub.add_parser("restart", help="Restart backend service")
    p_restart.set_defaults(fn=cmd_restart)

    # logs
    p_logs = sub.add_parser("logs", help="Tail backend logs")
    p_logs.add_argument("-n", "--lines", default=30, help="Number of lines")
    p_logs.set_defaults(fn=cmd_logs)

    # reload
    p_reload = sub.add_parser("reload", help="Reload nginx")
    p_reload.set_defaults(fn=cmd_reload)

    # tracks
    p_tracks = sub.add_parser("tracks", help="List tracks on VPS")
    p_tracks.add_argument("-n", "--limit", default=20, help="Max tracks to show")
    p_tracks.set_defaults(fn=cmd_tracks)

    # deploy-tracks
    p_dt = sub.add_parser("deploy-tracks", help="Deploy tracks from local directory to VPS")
    p_dt.add_argument("local", nargs="?", default="/root/vaporwave-radio/tracks", help="Local tracks directory")
    p_dt.set_defaults(fn=cmd_deploy_tracks)

    # deploy frontend
    p_deploy = sub.add_parser("deploy", help="Deploy DREAMWAVE frontend files to VPS")
    p_deploy.add_argument("local", nargs="?", default=LOCAL_REPO, help="Local DREAMWAVE repo directory")
    p_deploy.add_argument("--dry-run", action="store_true", help="Preview rsync changes without uploading")
    p_deploy.set_defaults(fn=cmd_deploy)

    # health
    p_health = sub.add_parser("health", help="Check API health endpoint")
    p_health.set_defaults(fn=cmd_health)

    # exec
    p_exec = sub.add_parser("exec", help="Run arbitrary command on VPS")
    p_exec.add_argument("command", help="Command to run")
    p_exec.set_defaults(fn=cmd_exec)
