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
    """Run a command on the DREAMWAVE VPS via SSH and return combined output."""
    _, output = ssh_result(host, cmd)
    return output


def ssh_result(host: str, cmd: str) -> tuple[int, Optional[str]]:
    """Run a command on the DREAMWAVE VPS via SSH and return exit code + output."""
    full_cmd = [
        "ssh", "-i", DREAMWAVE_KEY,
        *SSH_OPTIONS,
        f"{DREAMWAVE_USER}@{host}",
        cmd
    ]
    result = subprocess.run(full_cmd, capture_output=True, text=True)
    stdout = _strip_ssh_noise(result.stdout)
    stderr = _strip_ssh_noise(result.stderr)
    if stdout and stderr:
        return result.returncode, f"{stdout}\n{stderr}"
    return result.returncode, stdout or stderr


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


def _result_or_fail(output: Optional[str], *, failure_markers: tuple[str, ...], empty_failure: str | None = None, empty_success: str | None = None, exit_code: int = 0) -> str:
    cleaned = _strip_ssh_noise(output or "").strip()
    if not cleaned:
        if empty_failure is not None:
            return empty_failure
        return empty_success or ""
    if exit_code != 0 or _looks_like_failure(cleaned, failure_markers):
        return _fail_prefix(cleaned, empty_failure or "[FAIL] Remote command failed")
    return cleaned


def cmd_status(args) -> str:
    """Check backend and nginx status."""
    # Use is-active for a clean pass/fail check (no log noise)
    exit_code, backend_out = ssh_result(DREAMWAVE_HOST, "systemctl is-active dreamwave-backend")
    exit_code2, nginx_out = ssh_result(DREAMWAVE_HOST, "systemctl is-active nginx")

    backend_ok = backend_out.strip() == "active"
    nginx_ok = nginx_out.strip() == "active"

    if backend_ok and nginx_ok:
        return f"[OK] dreamwave-backend: active\n[OK] nginx: active"

    # Something is wrong — fetch detailed status for diagnosis
    lines = []
    if not backend_ok:
        lines.append(f"[FAIL] dreamwave-backend: {backend_out.strip() or 'unknown'}")
        _, detail = ssh_result(DREAMWAVE_HOST, "systemctl status dreamwave-backend --no-pager -l | head -20")
        if detail:
            lines.append(detail)
    if not nginx_ok:
        lines.append(f"[FAIL] nginx: {nginx_out.strip() or 'unknown'}")
        _, detail = ssh_result(DREAMWAVE_HOST, "systemctl status nginx --no-pager -l | head -20")
        if detail:
            lines.append(detail)

    return "\n".join(lines)


def cmd_restart(args) -> str:
    """Restart the backend service."""
    exit_code, out = ssh_result(DREAMWAVE_HOST, "systemctl restart dreamwave-backend && systemctl status dreamwave-backend --no-pager | head -20")
    return _result_or_fail(
        out,
        failure_markers=SSH_FAILURE_MARKERS + REMOTE_COMMAND_FAILURE_MARKERS,
        empty_success="Restart command sent",
        exit_code=exit_code,
    )


def cmd_logs(args) -> str:
    """Tail backend logs."""
    lines = args.lines
    exit_code, out = ssh_result(DREAMWAVE_HOST, f"journalctl -u dreamwave-backend --no-pager -n {lines}")
    return _result_or_fail(
        out,
        failure_markers=LOG_QUERY_FAILURE_MARKERS,
        empty_failure="[FAIL] Could not fetch logs",
        exit_code=exit_code,
    )


def cmd_reload(args) -> str:
    """Reload nginx."""
    exit_code, out = ssh_result(DREAMWAVE_HOST, "nginx -t && systemctl reload nginx")
    return _result_or_fail(
        out,
        failure_markers=SSH_FAILURE_MARKERS + REMOTE_COMMAND_FAILURE_MARKERS,
        empty_success="Reload command sent",
        exit_code=exit_code,
    )


def cmd_tracks(args) -> str:
    """List tracks on the VPS."""
    exit_code, out = ssh_result(DREAMWAVE_HOST, f"ls {DREAMWAVE_PATH}/tracks/*.mp3 | head {args.limit} && echo '---' && ssh {DREAMWAVE_USER}@{DREAMWAVE_HOST} 'ls {DREAMWAVE_PATH}/tracks/*.mp3 | wc -l'")
    return _result_or_fail(
        out,
        failure_markers=TRACKS_QUERY_FAILURE_MARKERS,
        empty_failure="[FAIL] Could not list tracks",
        exit_code=exit_code,
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
        "--exclude=node_modules",
        "--exclude=.env",
        "--exclude=backend/",
        "--exclude=tracks/",
        "--exclude=*.db",
        "--exclude=*.sqlite3",
        "--exclude=__pycache__",
        "--exclude=.pytest_cache",
        "--exclude=*.log",
    ]
    cmd = [
        "rsync", "-avz", "--delete",
        "-e", RSYNC_SSH,
    ] + excludes + [
        f"{local_repo}/",
        f"{DREAMWAVE_USER}@{DREAMWAVE_HOST}:{DREAMWAVE_PATH}/"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        out = f"[OK] Deployed to DREAMWAVE VPS\n{result.stdout[-500:]}"
        if dry_run:
            return out + "\n[DRY RUN] — no restart performed"
        reload = cmd_reload(args)
        if reload.startswith("[FAIL]"):
            return f"[FAIL] Deploy sync completed but reload failed\n{out}\n{reload}"
        return out + "\n" + reload
    return f"[FAIL] rsync failed:\n{result.stderr[-300:]}"


def register(subparsers):
    """Register dreamwave subcommands."""
    p_dreamwave = subparsers.add_parser("dreamwave", help="DREAMWAVE FM — 38.45.71.55")

    sub = p_dreamwave.add_subparsers(dest="dw_cmd", required=True)

    p_status = sub.add_parser("status", help="Check backend and nginx status")
    p_status.set_defaults(fn=cmd_status)

    p_restart = sub.add_parser("restart", help="Restart the backend service")
    p_restart.set_defaults(fn=cmd_restart)

    p_logs = sub.add_parser("logs", help="Tail backend logs")
    p_logs.add_argument("-n", "--lines", type=int, default=30, dest="lines",
                        help="Number of lines to tail")
    p_logs.set_defaults(fn=cmd_logs)

    p_reload = sub.add_parser("reload", help="Reload nginx")
    p_reload.set_defaults(fn=cmd_reload)

    p_tracks = sub.add_parser("tracks", help="List tracks on the VPS")
    p_tracks.add_argument("-l", "--limit", type=int, default=20, dest="limit",
                          help="Max tracks to list")
    p_tracks.set_defaults(fn=cmd_tracks)

    p_deploy_tracks = sub.add_parser("deploy-tracks", help="Deploy tracks from local to VPS")
    p_deploy_tracks.add_argument("local", nargs="?", default="/root/vaporwave-radio/tracks",
                                 help="Local tracks directory")
    p_deploy_tracks.set_defaults(fn=cmd_deploy_tracks)

    p_deploy = sub.add_parser("deploy", help="Deploy frontend files from local repo to VPS")
    p_deploy.add_argument("local", nargs="?", default="/root/vaporwave-radio",
                          help="Local repo directory")
    p_deploy.add_argument("--dry-run", action="store_true", help="Show what would be copied")
    p_deploy.set_defaults(fn=cmd_deploy)
