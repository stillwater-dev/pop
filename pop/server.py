"""SSH server connection and command execution."""

import os
import shlex
from pathlib import Path
from typing import Optional, Dict, List, TYPE_CHECKING

import paramiko
from scp import SCPClient

from .config import get_server_config
from .commands import run_playbook as _run_playbook, load_playbook

if TYPE_CHECKING:
    from .commands import "Server"


class Server:
    """Represents a remote VPS server."""

    def __init__(
        self,
        host: str,
        user: str,
        port: int = 22,
        key_path: Optional[str] = None,
        password: Optional[str] = None,
        name: str = "",
    ):
        self.host = host
        self.user = user
        self.port = port
        self.key_path = os.path.expanduser(key_path) if key_path else None
        self.password = password
        self.name = name
        self.client: Optional[paramiko.SSHClient] = None

    @classmethod
    def from_config(cls, config_path: Optional[str], name: str) -> "Server":
        """Load a server from a config file."""
        cfg = get_server_config(name, config_path)
        return cls(
            host=cfg["host"],
            user=cfg.get("user", "root"),
            port=cfg.get("port", 22),
            key_path=cfg.get("key"),
            password=cfg.get("password"),
            name=name,
        )

    def connect(self):
        """Establish SSH connection."""
        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict = {
            "hostname": self.host,
            "port": self.port,
            "username": self.user,
        }

        if self.key_path:
            connect_kwargs["key_filename"] = self.key_path
        elif self.password:
            connect_kwargs["password"] = self.password
        else:
            connect_kwargs["look_for_keys"] = True

        self.client.connect(**connect_kwargs)
        return self

    def run(
        self,
        command: str,
        bg: bool = False,
        timeout: Optional[int] = None,
    ) -> str:
        """Run a shell command and return stdout."""
        if not self.client:
            self.connect()

        if bg:
            channel = self.client.get_transport().open_session()
            channel.exec_command(command)
            return f"[background] Command started on {self.name}"

        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if err:
            return out + "\n[stderr] " + err
        return out

    def exec_script(self, script_path: Path) -> str:
        """Upload and execute a local script on the server."""
        if not self.client:
            self.connect()

        script_path = script_path.expanduser().resolve()
        remote_path = f"/tmp/{script_path.name}"

        self.upload(str(script_path), remote_path)
        self.run(f"chmod +x {remote_path}")

        stdin, stdout, stderr = self.client.exec_command(f"bash {remote_path}")
        out = stdout.read().decode()
        err = stderr.read().decode()

        self.run(f"rm -f {remote_path}")

        if err:
            return out + "\n[stderr] " + err
        return out

    def upload(self, local_path: str, remote_path: str):
        """Upload a file or directory to the server."""
        if not self.client:
            self.connect()

        local_path = os.path.expanduser(local_path)
        with SCPClient(self.client.get_transport()) as scp:
            scp.put(local_path, remote_path)

    def download(self, remote_path: str, local_path: str):
        """Download a file from the server."""
        if not self.client:
            self.connect()

        local_path = os.path.expanduser(local_path)
        with SCPClient(self.client.get_transport()) as scp:
            scp.get(remote_path, local_path)

    def run_playbook(self, playbook_path: Path, extra_vars: Optional[dict] = None) -> str:
        """Execute a playbook YAML file on the server."""
        if not self.client:
            self.connect()
        return _run_playbook(self, playbook_path, extra_vars)

    def close(self):
        """Close the SSH connection."""
        if self.client:
            self.client.close()
            self.client = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()
