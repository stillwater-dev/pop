"""Pluggable service loader for pop — reads services from YAML config."""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict

SERVICES_CONFIG = Path(__file__).parent.parent / "services.yaml"


def load_services() -> dict:
    """Load all service definitions from YAML config."""
    if not SERVICES_CONFIG.exists():
        return {}
    try:
        with open(SERVICES_CONFIG) as f:
            data = yaml.safe_load(f)
        return data.get("services", {})
    except Exception:
        return {}


def get_service(name: str) -> Optional[dict]:
    """Get a single service definition by name."""
    services = load_services()
    return services.get(name)


def list_services() -> list:
    """List all registered service names."""
    return list(load_services().keys())


def resolve_ssh_config(name: str) -> dict:
    """Resolve SSH connection config for a service."""
    svc = get_service(name)
    if not svc:
        return {}
    return {
        "host": svc.get("host", ""),
        "user": svc.get("user", "root"),
        "key": os.path.expanduser(svc.get("key", "~/.ssh/id_ed25519")),
        "port": svc.get("port", 22),
    }
