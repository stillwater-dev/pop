"""Hermés Library management commands for pop."""

import subprocess
from typing import Optional

HERMES_HOST = "10.0.69.236"
HERMES_USER = "root"
HERMES_KEY = "/root/.ssh/id_ed25519"
HERMES_CONTAINER = "hermes-library"
HERMES_PORT = 8081
LOCAL_REPO = "/root/hermes-library"
VPS_STACK_DIR = "/opt/stacks/hermes-library"
CONTAINER_FRONTEND = "/app/frontend"
CONTAINER_BACKEND = "/app/main.py"
CONTAINER_EXTENSIONS = "/app/extensions"

SSH_OPTIONS = [
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=5",
]

SSH_FAILURE_MARKERS = (
    "host key verification failed",
    "permission denied",
    "could not resolve hostname",
    "connection refused",
    "connection timed out",
    "no route to host",
    "operation timed out",
    "ssh:",
)


def _ssh(cmd: str) -> subprocess.CompletedProcess:
    """Run an SSH command on the Hermes VPS."""
    return subprocess.run(
        ["ssh", "-i", HERMES_KEY, *SSH_OPTIONS, f"{HERMES_USER}@{HERMES_HOST}", cmd],
        capture_output=True, text=True, timeout=30
    )


def _docker_exec(cmd: str) -> subprocess.CompletedProcess:
    """Run a docker exec command inside the Hermes container."""
    return _ssh(f"docker exec {HERMES_CONTAINER} {cmd}")


def _is_ssh_failure(stderr: str) -> bool:
    stderr_lower = (stderr or "").lower()
    return any(m in stderr_lower for m in SSH_FAILURE_MARKERS)


def _fail(msg: str) -> str:
    return f"[FAIL] {msg}"


def status() -> str:
    """Check Hermés Library health and container status."""
    result = _ssh(f"docker ps --filter name={HERMES_CONTAINER} --format '{{{{.Status}}}}'")
    if _is_ssh_failure(result.stderr):
        return _fail(f"SSH failure: {result.stderr.strip()}")

    container_status = result.stdout.strip()
    if not container_status:
        return _fail(f"Container {HERMES_CONTAINER} not running")

    # Check API health
    health = _ssh(f"curl -s http://localhost:{HERMES_PORT}/api/health")
    if health.returncode != 0 or '"status":"ok"' not in health.stdout:
        return f"[DOWN] Container running but API unhealthy\n  Status: {container_status}"

    # Get book count and extensions
    books = _ssh(f"curl -s http://localhost:{HERMES_PORT}/api/books | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d.get('books',[])))\" 2>/dev/null")
    exts = _ssh(f"curl -s http://localhost:{HERMES_PORT}/api/extensions | python3 -c \"import sys,json; d=json.load(sys.stdin); print(len(d.get('extensions',[])))\" 2>/dev/null")

    return (
        f"[OK] Hermés Library healthy\n"
        f"  Container: {container_status}\n"
        f"  Books: {books.stdout.strip()}\n"
        f"  Extensions: {exts.stdout.strip()}"
    )


def deploy(frontend: bool = True, backend: bool = True, extensions: bool = True, full: bool = False) -> str:
    """Deploy Hermés Library changes to the VPS."""
    from pathlib import Path
    local = Path(LOCAL_REPO)
    if not local.exists():
        return _fail(f"Local repo not found: {LOCAL_REPO}")

    results = []

    # Copy files to VPS stack dir
    if frontend or full:
        tar_result = subprocess.run(
            ["tar", "cf", "-", "frontend/"],
            capture_output=True, cwd=str(local), timeout=10
        )
        if tar_result.returncode != 0:
            return _fail(f"tar failed: {tar_result.stderr.decode()}")

        ssh_proc = subprocess.run(
            ["ssh", "-i", HERMES_KEY, *SSH_OPTIONS, f"{HERMES_USER}@{HERMES_HOST}",
             f"cd {VPS_STACK_DIR} && tar xf -"],
            input=tar_result.stdout, capture_output=True, text=True, timeout=15
        )
        if _is_ssh_failure(ssh_proc.stderr):
            return _fail(f"SSH failure copying frontend: {ssh_proc.stderr.strip()}")

        # Copy into container
        for f in ["styles.css", "app.js", "index.html"]:
            cp = _ssh(f"docker cp {VPS_STACK_DIR}/frontend/{f} {HERMES_CONTAINER}:{CONTAINER_FRONTEND}/{f}")
            if cp.returncode != 0:
                results.append(f"[FAIL] docker cp frontend/{f}")
            else:
                results.append(f"[OK] frontend/{f}")

    if backend or full:
        # Copy main.py
        cp = _ssh(f"docker cp {VPS_STACK_DIR}/backend/main.py {HERMES_CONTAINER}:{CONTAINER_BACKEND}")
        if cp.returncode != 0:
            results.append(f"[FAIL] docker cp backend/main.py")
        else:
            results.append(f"[OK] backend/main.py")

    if extensions or full:
        for ext in ["epub-converter", "device-sync", "manga-reader", "calibre-sync", "metadata-plus"]:
            cp = _ssh(f"docker cp {VPS_STACK_DIR}/backend/extensions/{ext} {HERMES_CONTAINER}:{CONTAINER_EXTENSIONS}/{ext}")
            results.append(f"[OK] extensions/{ext}" if cp.returncode == 0 else f"[FAIL] extensions/{ext}")
        # Copy __init__.py too
        _ssh(f"docker cp {VPS_STACK_DIR}/backend/extensions/__init__.py {HERMES_CONTAINER}:{CONTAINER_EXTENSIONS}/__init__.py")

    # Restart
    restart = _ssh(f"docker restart {HERMES_CONTAINER}")
    if restart.returncode != 0:
        results.append(f"[FAIL] docker restart")
    else:
        results.append(f"[OK] container restarted")

    # Health check
    import time
    time.sleep(3)
    health = _ssh(f"curl -s http://localhost:{HERMES_PORT}/api/health")
    if health.returncode == 0 and '"status":"ok"' in health.stdout:
        results.append(f"[OK] health check passed")
    else:
        results.append(f"[FAIL] health check")

    return "Hermés Library deploy:\n  " + "\n  ".join(results)


def logs(lines: int = 50) -> str:
    """Show recent container logs."""
    result = _ssh(f"docker logs --tail {lines} {HERMES_CONTAINER}")
    if _is_ssh_failure(result.stderr):
        return _fail(f"SSH failure: {result.stderr.strip()}")
    if result.returncode != 0:
        return _fail(f"docker logs failed: {result.stderr.strip()}")
    return result.stdout.strip()


def restart() -> str:
    """Restart the Hermés Library container."""
    result = _ssh(f"docker restart {HERMES_CONTAINER} && sleep 2 && curl -s http://localhost:{HERMES_PORT}/api/health")
    if _is_ssh_failure(result.stderr):
        return _fail(f"SSH failure: {result.stderr.strip()}")
    if result.returncode != 0 or '"status":"ok"' not in result.stdout:
        return _fail(f"Restart failed: {result.stdout.strip()}")
    return "[OK] Restarted and healthy"


def test() -> str:
    """Run the test suite against the live server."""
    import sys
    test_path = Path(LOCAL_REPO) / "tests" / "test_api.py"
    if not test_path.exists():
        return _fail(f"Tests not found: {test_path}")

    result = subprocess.run(
        [sys.executable, str(test_path)],
        capture_output=True, text=True, timeout=60, cwd=str(Path(LOCAL_REPO))
    )
    if result.returncode == 0:
        passed = result.stdout.count("... ok") + result.stdout.count("PASSED")
        total = result.stdout.count("test_")
        return f"[OK] All tests passed\n{result.stdout.strip().split(chr(10))[-5:]}"
    else:
        # Return last 20 lines
        lines = (result.stdout + result.stderr).strip().split("\n")
        return _fail(f"Tests failed\n" + "\n".join(lines[-15:]))


def add_hermes_subparser(subparsers):
    """Register the hermes subcommand."""
    hermes = subparsers.add_parser("hermes", help="Hermés Library management")
    hermes_subs = hermes.add_subparsers(dest="hermes_action")

    hermes_subs.add_parser("status", help="Check health and status")
    hermes_subs.add_parser("logs", help="Show recent container logs")
    hermes_subs.add_parser("restart", help="Restart the container")
    hermes_subs.add_parser("test", help="Run API tests")
    hermes_subs.add_parser("deploy", help="Deploy frontend + backend")

    hermes.set_defaults(func=handle_hermes)


def handle_hermes(args):
    """Handle hermes subcommand."""
    action = getattr(args, "hermes_action", "status")
    if action == "status":
        print(status())
    elif action == "logs":
        print(logs())
    elif action == "restart":
        print(restart())
    elif action == "test":
        print(test())
    elif action == "deploy":
        print(deploy())
    else:
        print(status())
