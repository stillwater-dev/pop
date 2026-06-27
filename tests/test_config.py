# tests/test_config.py
"""Tests for pop.config module."""

import pytest
from pathlib import Path
from pop.config import load_config, list_configs, get_server_config


class TestLoadConfig:
    """Config loading tests."""

    def test_load_config_returns_dict(self, tmp_path):
        """load_config returns a dictionary."""
        cfg_file = tmp_path / "pop.yaml"
        cfg_file.write_text("servers:\n  - name: test\n    host: 127.0.0.1\n")
        result = load_config(str(cfg_file))
        assert isinstance(result, dict)

    def test_load_config_raises_on_missing_file(self):
        """load_config raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path.yaml")

    def test_list_configs_returns_servers(self, tmp_path):
        """list_configs returns list of server dicts."""
        cfg_file = tmp_path / "pop.yaml"
        cfg_file.write_text("servers:\n  - name: web\n    host: 1.2.3.4\n")
        result = list_configs(str(cfg_file))
        assert isinstance(result, list)
        assert result[0]["name"] == "web"

    def test_list_configs_returns_empty_on_missing_file(self):
        """list_configs returns empty list when config missing."""
        result = list_configs("/nonexistent/path.yaml")
        assert result == []

    def test_get_server_config_returns_server(self, tmp_path):
        """get_server_config returns specific server by name."""
        cfg_file = tmp_path / "pop.yaml"
        cfg_file.write_text("servers:\n  - name: web\n    host: 1.2.3.4\n")
        result = get_server_config("web", str(cfg_file))
        assert result["name"] == "web"
        assert result["host"] == "1.2.3.4"

    def test_get_server_config_raises_on_missing(self, tmp_path):
        """get_server_config raises KeyError for unknown server."""
        cfg_file = tmp_path / "pop.yaml"
        cfg_file.write_text("servers:\n  - name: web\n    host: 1.2.3.4\n")
        with pytest.raises(KeyError):
            get_server_config("nonexistent", str(cfg_file))
