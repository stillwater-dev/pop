"""DREAMWAVE FM management commands."""

import subprocess
from typing import Optional

# DREAMWAVE VPS defaults
DREAMWAVE_HOST = "38.45.71.55"
DREAMWAVE_USER = "root"
DREAMWAVE_KEY = "/root/.ssh/id_ed25519"
DREAMWAVE_PATH = "/var/www/dreamwave"
DREAMWAVE_PORT = 22


def ssh(host: str, cmd: str, capture: bool = True) -> Optional[str]:
    """Run a command on the DREAMWAVE VPS via SSH."""
    full_cmd = [
        "ssh", "-i", DREAMWAVE_KEY,
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=5",
        f"{DREAMWAVE_USER}@{host}",
        cmd
    ]
    result = subprocess.run(full_cmd, capture_output=capture, text=True)
    if capture:
        return result.stdout + (result.stderr if result.stderr else "")
    return None


def cmd_status(args) -> str:
    """Check backend and nginx status."""
    out = ssh(DREAMWAVE_HOST, "systemctl status dreamwave-backend --no-pager -l; echo '---'; systemctl status nginx --no-pager -l | head -10")
    return out or "Could not connect to DREAMWAVE VPS"


def cmd_restart(args) -> str:
    """Restart the backend service."""
    out = ssh(DREAMWAVE_HOST, "systemctl restart dreamwave-backend && systemctl status dreamwave-backend --no-pager | head -20")
    return out or "Restart command sent"


def cmd_logs(args) -> str:
    """Tail backend logs."""
    lines = args.lines
    out = ssh(DREAMWAVE_HOST, f"journalctl -u dreamwave-backend --no-pager -n {lines}")
    return out or "Could not fetch logs"


def cmd_reload(args) -> str:
    """Reload nginx."""
    out = ssh(DREAMWAVE_HOST, "nginx -t && systemctl reload nginx")
    return out or "Reload command sent"


def cmd_tracks(args) -> str:
    """List tracks on the VPS."""
    out = ssh(DREAMWAVE_HOST, f"ls {DREAMWAVE_PATH}/tracks/*.mp3 | head {args.limit} && echo '---' && ssh {DREAMWAVE_USER}@{DREAMWAVE_HOST} 'ls {DREAMWAVE_PATH}/tracks/*.mp3 | wc -l'")
    return out or "Could not list tracks"


def cmd_deploy_tracks(args) -> str:
    """Deploy new tracks from local /root/vaporwave-radio/tracks/ to VPS."""
    local_tracks = args.local
    
    # Check local tracks exist
    check = subprocess.run(["ls", local_tracks], capture_output=True)
    if check.returncode != 0:
        return f"Local tracks directory not found: {local_tracks}"
    
    count = subprocess.run(["ls", f"{local_tracks}/*.mp3"], shell=True, capture_output=True, text=True)
    mp3_count = len([l for l in count.stdout.strip().split("\n") if l.endswith(".mp3")])
    
    # rsync tracks to VPS
    cmd = [
        "rsync", "-avz", "--progress",
        "-e", f"ssh -i {DREAMWAVE_KEY} -o StrictHostKeyChecking=no",
        f"{local_tracks}/",
        f"{DREAMWAVE_USER}@{DREAMWAVE_HOST}:{DREAMWAVE_PATH}/tracks/"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return f"Deploy failed: {result.stderr}"
    return f"Deployed {mp3_count} tracks.\n{result.stdout[-500:]}"


def cmd_health(args) -> str:
    """Check API health endpoint."""
    import urllib.request
    try:
        resp = urllib.request.urlopen(f"http://{DREAMWAVE_HOST}/api/health", timeout=5)
        return f"API OK: {resp.read().decode()}"
    except Exception as e:
        return f"API health check failed: {e}"


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

    # health
    p_health = sub.add_parser("health", help="Check API health endpoint")
    p_health.set_defaults(fn=cmd_health)

    # exec
    p_exec = sub.add_parser("exec", help="Run arbitrary command on VPS")
    p_exec.add_argument("command", help="Command to run")
    p_exec.set_defaults(fn=cmd_exec)
