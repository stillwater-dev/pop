"""Playbook and command execution utilities."""

import yaml
from pathlib import Path
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .server import Server


def load_playbook(path: Path) -> Dict:
    """Load a playbook YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def run_playbook(server: "Server", playbook_path: Path, extra_vars: Optional[Dict] = None) -> str:
    """Execute a playbook on a server.
    
    Playbook format:
        steps:
          - name: "Install Docker"
            command: "curl -fsSL https://get.docker.com | sh"
          - name: "Clone repo"
            command: "git clone https://github.com/user/repo.git /opt/repo"
            cwd: "/opt/repo"
    """
    playbook = load_playbook(playbook_path)
    vars = {**(playbook.get("vars", {})), **(extra_vars or {})}
    results = []

    for step in playbook.get("steps", []):
        name = step.get("name", "step")
        cmd = step.get("command", "")
        cwd = step.get("cwd")

        # Substitute {{ var }} variables
        for k, v in vars.items():
            cmd = cmd.replace(f"{{{{ {k} }}}}", str(v))
            cmd = cmd.replace(f"{{{{{k}}}}}", str(v))

        if cwd:
            cmd = f"cd {cwd} && {cmd}"

        results.append(f"\n=== {name} ===")
        results.append(f"$ {cmd}")
        out = server.run(cmd)
        results.append(out)

    return "\n".join(results)


def run_command(server: "Server", command: str, bg: bool = False) -> str:
    """Run a single command."""
    return server.run(command, bg=bg)


def upload_file(server: "Server", local: str, remote: str):
    """Upload a file."""
    server.upload(local, remote)
