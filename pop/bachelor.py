"""Bachelor Party App management commands — targets VPS at 5.181.177.113."""

import subprocess
import time
import urllib.request


BACHELOR_HOST = "5.181.177.113"
SSH_KEY = "/root/.hermes/bachelor/bachelor_ed25519"
LOCAL_REPO = "/root/bachelor_party"
VPS_APP_DIR = "/root/bachelor_party"


def ssh(cmd: str) -> str:
    """Run a command on the bachelor VPS via SSH."""
    result = subprocess.run(
        ["ssh", "-i", SSH_KEY, "-o", "StrictHostKeyChecking=no",
         f"root@{BACHELOR_HOST}", cmd],
        capture_output=True, text=True
    )
    return result.stdout + result.stderr


def cmd_status(args) -> str:
    """Check app status on VPS."""
    out = ssh("ps aux | grep 'http.server' | grep -v grep")
    if "http.server" in out:
        pid = out.split()[1]
        return f"[OK] http.server running (PID {pid})\n  URL: http://5.181.177.113/bachelor_party_app.html"
    return "[DOWN] http.server not running"


def cmd_start(args) -> str:
    """Start http.server on VPS (port 80, serving /root)."""
    # Check if already running
    out = ssh("ps aux | grep 'http.server' | grep -v grep")
    if "http.server" in out:
        pid = out.split()[1]
        return f"Already running (PID {pid})"

    # Kill any stale process on port 80
    ssh("pkill -f 'http.server 80' 2>/dev/null; sleep 1")
    out = ssh("nohup python3 -m http.server 80 --directory /root > /var/log/bachelor.log 2>&1 & sleep 2 && ps aux | grep 'http.server' | grep -v grep")
    if "http.server" in out:
        pid = out.split()[1]
        return f"[OK] http.server started on port 80 (PID {pid})"
    return "[FAIL] Could not start server"


def cmd_stop(args) -> str:
    """Stop http.server on VPS."""
    out = ssh("ps aux | grep 'http.server' | grep -v grep")
    if "http.server" not in out:
        return "http.server not running"
    pid = out.strip().split()[1]
    ssh(f"kill {pid}")
    time.sleep(1)
    out2 = ssh("ps aux | grep 'http.server' | grep -v grep")
    if "http.server" in out2:
        return f"[WARN] Process still running (PID {out2.split()[1]})"
    return f"[OK] Stopped (was PID {pid})"


def cmd_restart(args) -> str:
    """Restart http.server on VPS."""
    stop = cmd_stop(args)
    start = cmd_start(args)
    return f"{stop}\n{start}"


def cmd_health(args) -> str:
    """Check if app responds."""
    try:
        resp = urllib.request.urlopen("http://5.181.177.113/bachelor_party_app.html", timeout=5)
        html = resp.read().decode()[:300]
        title_start = html.find("<title>")
        title_end = html.find("</title>")
        if title_start != -1:
            title = html[title_start + 7:title_end]
        else:
            title = "(no title)"
        return f"OK: HTTP {resp.status}\nTitle: {title}"
    except Exception as e:
        return f"FAIL: {e}"


def cmd_logs(args) -> str:
    """Get recent logs from VPS."""
    return ssh("tail -30 /var/log/bachelor.log")


def cmd_exec(args) -> str:
    """Run a command on the VPS in the app directory."""
    return ssh(f"cd {VPS_APP_DIR} && {args.command}")


def cmd_deploy(args) -> str:
    """Deploy latest bachelor_party files from local repo to VPS via rsync."""
    excludes = [
        "--exclude=__pycache__",
        "--exclude=*.pyc",
        "--exclude=*.pyo",
        "--exclude=.git",
        "--exclude=tests/",
        "--exclude=.pytest_cache",
        "--exclude=*.log",
    ]
    cmd = [
        "rsync", "-avz", "--delete",
        "-e", f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no",
    ] + excludes + [
        f"{LOCAL_REPO}/",
        f"root@{BACHELOR_HOST}:{VPS_APP_DIR}/"
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        out = f"[OK] Deployed to VPS\n{result.stdout[-500:]}"
        if getattr(args, "dry_run", False):
            return out + "\n[DRY RUN] — no restart performed"
        restart = cmd_restart(args)
        return out + "\n" + restart
    return f"[FAIL] rsync failed:\n{result.stderr[-300:]}"


def cmd_vps_status(args) -> str:
    """Full VPS status: disk, uptime, app."""
    out = ssh("df -h / && echo '---' && uptime && echo '---' && ps aux | grep 'http.server' | grep -v grep")
    return out


def register(subparsers):
    """Register bachelor subcommands."""
    p_bachelor = subparsers.add_parser("bachelor", help="Bachelor Party App — 5.181.177.113")

    sub = p_bachelor.add_subparsers(dest="bp_cmd", required=True)

    p_status = sub.add_parser("status", help="Check app status")
    p_status.set_defaults(fn=cmd_status)

    p_start = sub.add_parser("start", help="Start http.server on VPS")
    p_start.set_defaults(fn=cmd_start)

    p_stop = sub.add_parser("stop", help="Stop http.server on VPS")
    p_stop.set_defaults(fn=cmd_stop)

    p_restart = sub.add_parser("restart", help="Restart http.server")
    p_restart.set_defaults(fn=cmd_restart)

    p_health = sub.add_parser("health", help="Check if app responds")
    p_health.set_defaults(fn=cmd_health)

    p_logs = sub.add_parser("logs", help="Tail recent logs")
    p_logs.set_defaults(fn=cmd_logs)

    p_vps_status = sub.add_parser("vps-status", help="Full VPS status (disk/uptime/app)")
    p_vps_status.set_defaults(fn=cmd_vps_status)

    p_deploy = sub.add_parser("deploy", help="Deploy local repo to VPS via rsync + restart")
    p_deploy.set_defaults(fn=cmd_deploy)
    p_deploy.add_argument("--dry-run", action="store_true", help="Show what would be copied")

    p_exec = sub.add_parser("exec", help="Run command on VPS in app dir")
    p_exec.add_argument("command", nargs="+", help="Command to run")
    p_exec.set_defaults(fn=cmd_exec)
