"""Bachelor Party App management commands."""

import subprocess
import os
import signal
import time
import urllib.request
from pathlib import Path

# Bachelor app defaults
BACHELOR_DIR = "/root/bachelor_party"
BACHELOR_PORT = 8765
BACHELOR_TUNNEL_PORT = 7400
BACHELOR_SUBDOMAIN = "wilmington-bachelor"
LT_BIN = "/root/.npm/_npx/75ac80b86e83d4a2/node_modules/.bin/lt"


def find_httpd_pid(port: int) -> str | None:
    """Find PID of http.server on a port."""
    result = subprocess.run(
        ["ss", "-tlnp", f"sport = :{port}"],
        capture_output=True, text=True
    )
    for line in result.stdout.split("\n"):
        if f":{port}" in line:
            # Extract PID from ss output
            parts = line.split()
            for p in parts:
                if "pid=" in p:
                    return p.split("=")[1].split(",")[0]
    return None


def find_lt_pid(subdomain: str) -> str | None:
    """Find PID of localtunnel process by subdomain."""
    result = subprocess.run(
        ["pgrep", "-a", "lt"],
        capture_output=True, text=True
    )
    for line in result.stdout.split("\n"):
        if subdomain in line:
            parts = line.split()
            if parts:
                return parts[0]
    return None


def cmd_status(args) -> str:
    """Check if app and tunnel are running."""
    lines = []

    # Check HTTP server
    pid = find_httpd_pid(BACHELOR_PORT)
    if pid:
        lines.append(f"[OK] HTTP server running on port {BACHELOR_PORT} (PID {pid})")
    else:
        lines.append(f"[DOWN] HTTP server NOT running on port {BACHELOR_PORT}")

    # Check tunnel
    lt_pid = find_lt_pid(BACHELOR_SUBDOMAIN)
    if lt_pid:
        lines.append(f"[OK] Localtunnel running (PID {lt_pid})")
        lines.append(f"     URL: https://{BACHELOR_SUBDOMAIN}.loca.lt")
    else:
        lines.append(f"[DOWN] Localtunnel NOT running")

    # Check if responding
    try:
        resp = urllib.request.urlopen(f"http://localhost:{BACHELOR_PORT}/", timeout=3)
        lines.append(f"[OK] App responding: HTTP {resp.status}")
    except Exception as e:
        lines.append(f"[DOWN] App not responding: {e}")

    return "\n".join(lines)


def cmd_start(args) -> str:
    """Start the bachelor app HTTP server."""
    pid = find_httpd_pid(BACHELOR_PORT)
    if pid:
        return f"HTTP server already running on port {BACHELOR_PORT} (PID {pid})"

    # Start server
    cmd = ["python3", "-m", "http.server", str(BACHELOR_PORT)]
    proc = subprocess.Popen(
        cmd,
        cwd=BACHELOR_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    time.sleep(1)

    # Verify
    pid = find_httpd_pid(BACHELOR_PORT)
    if pid:
        return f"HTTP server started on port {BACHELOR_PORT} (PID {pid})"
    return "HTTP server failed to start"


def cmd_stop(args) -> str:
    """Stop the bachelor app HTTP server."""
    pid = find_httpd_pid(BACHELOR_PORT)
    if not pid:
        return f"HTTP server not running on port {BACHELOR_PORT}"

    os.kill(int(pid), signal.SIGTERM)
    time.sleep(1)
    pid2 = find_httpd_pid(BACHELOR_PORT)
    if pid2:
        return f"Warning: server may still be running (PID {pid2})"
    return f"HTTP server stopped (was PID {pid})"


def cmd_tunnel_start(args) -> str:
    """Start localtunnel to expose the app."""
    lt_pid = find_lt_pid(BACHELOR_SUBDOMAIN)
    if lt_pid:
        return f"Localtunnel already running (PID {lt_pid}) at https://{BACHELOR_SUBDOMAIN}.loca.lt"

    # Kill stale lt processes first
    subprocess.run(["pkill", "-f", "lt --port 7400"], capture_output=True)
    time.sleep(1)

    cmd = [
        "nohup", "node",
        LT_BIN,
        "--port", str(BACHELOR_TUNNEL_PORT),
        "--subdomain", BACHELOR_SUBDOMAIN,
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid
    )
    time.sleep(3)

    lt_pid = find_lt_pid(BACHELOR_SUBDOMAIN)
    if lt_pid:
        return f"Localtunnel started: https://{BACHELOR_SUBDOMAIN}.loca.lt (PID {lt_pid})"
    return "Localtunnel failed to start"


def cmd_tunnel_stop(args) -> str:
    """Stop localtunnel."""
    lt_pid = find_lt_pid(BACHELOR_SUBDOMAIN)
    if not lt_pid:
        return "Localtunnel not running"

    os.kill(int(lt_pid), signal.SIGTERM)
    time.sleep(1)
    lt_pid2 = find_lt_pid(BACHELOR_SUBDOMAIN)
    if lt_pid2:
        return f"Warning: tunnel may still be running (PID {lt_pid2})"
    return f"Localtunnel stopped (was PID {lt_pid})"


def cmd_restart(args) -> str:
    """Restart HTTP server."""
    stop = cmd_stop(args)
    start = cmd_start(args)
    return f"{stop}\n{start}"


def cmd_tunnel_restart(args) -> str:
    """Restart localtunnel."""
    stop = cmd_tunnel_stop(args)
    start = cmd_tunnel_start(args)
    return f"{stop}\n{start}"


def cmd_full_restart(args) -> str:
    """Full restart: server + tunnel."""
    stop_s = cmd_stop(args)
    stop_t = cmd_tunnel_stop(args)
    start_s = cmd_start(args)
    start_t = cmd_tunnel_start(args)
    return f"{stop_s}\n{stop_t}\n{start_s}\n{start_t}"


def cmd_health(args) -> str:
    """Check if app responds."""
    try:
        resp = urllib.request.urlopen(f"http://localhost:{BACHELOR_PORT}/", timeout=5)
        html = resp.read().decode()[:200]
        return f"OK: HTTP {resp.status}\nTitle snippet: {html[html.find('<title>')+7:html.find('</title>')][:60]}"
    except Exception as e:
        return f"FAIL: {e}"


def cmd_exec(args) -> str:
    """Run a command on the app directory."""
    result = subprocess.run(
        args.command,
        shell=True,
        cwd=BACHELOR_DIR,
        capture_output=True, text=True
    )
    return result.stdout + (result.stderr if result.stderr else "")


def register(subparsers):
    """Register bachelor subcommands."""
    p_bp = subparsers.add_parser("bachelor", help="Bachelor Party App management")
    p_bp.set_defaults(fn=lambda a: p_bp.print_help())

    sub = p_bp.add_subparsers(dest="bp_cmd", required=True)

    sub.add_parser("status", help="Check app + tunnel status").set_defaults(fn=cmd_status)
    sub.add_parser("start", help="Start HTTP server").set_defaults(fn=cmd_start)
    sub.add_parser("stop", help="Stop HTTP server").set_defaults(fn=cmd_stop)
    sub.add_parser("restart", help="Restart HTTP server").set_defaults(fn=cmd_restart)
    sub.add_parser("tunnel-start", help="Start localtunnel").set_defaults(fn=cmd_tunnel_start)
    sub.add_parser("tunnel-stop", help="Stop localtunnel").set_defaults(fn=cmd_tunnel_stop)
    sub.add_parser("tunnel-restart", help="Restart localtunnel").set_defaults(fn=cmd_tunnel_restart)
    sub.add_parser("full-restart", help="Full restart: server + tunnel").set_defaults(fn=cmd_full_restart)
    sub.add_parser("health", help="Check if app responds").set_defaults(fn=cmd_health)

    p_exec = sub.add_parser("exec", help="Run command in app directory")
    p_exec.add_argument("command", help="Command to run")
    p_exec.set_defaults(fn=cmd_exec)
