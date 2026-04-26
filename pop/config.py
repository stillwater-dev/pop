"""Config loading and management."""

import os
import yaml
from pathlib import Path
from typing import List, Dict, Optional


DEFAULT_CONFIG_PATH = Path(os.path.expanduser("~/.pop.yaml"))


def load_config(path: Optional[str] = None) -> Dict:
    """Load config from YAML file."""
    cfg_path = Path(path or os.environ.get("POP_CONFIG", str(DEFAULT_CONFIG_PATH)))
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def list_configs(path: Optional[str] = None) -> List[Dict]:
    """List all server configs."""
    try:
        cfg = load_config(path)
        return cfg.get("servers", [])
    except FileNotFoundError:
        return []


def get_server_config(name: str, path: Optional[str] = None) -> Dict:
    """Get a specific server config by name."""
    cfg = load_config(path)
    servers = cfg.get("servers", [])
    for s in servers:
        if s.get("name") == name:
            return s
    raise KeyError(f"Server '{name}' not found in config")
