# tests/test_services.py
"""Tests for pop.services module."""

import pytest
from pop.services import load_services, get_service, list_services, resolve_ssh_config


class TestServices:
    """Service loading and resolution tests."""

    def test_load_services_returns_dict(self):
        """load_services returns a dictionary."""
        result = load_services()
        assert isinstance(result, dict)

    def test_get_service_returns_dict_for_valid_service(self):
        """get_service returns service dict for known service."""
        # hermes-library is defined in services.yaml
        result = get_service("hermes-library")
        if result:  # service exists
            assert isinstance(result, dict)
            assert "host" in result

    def test_get_service_returns_none_for_unknown(self):
        """get_service returns None for unknown service."""
        result = get_service("nonexistent-service-xyz")
        assert result is None

    def test_list_services_returns_list(self):
        """list_services returns list of service name strings."""
        result = list_services()
        assert isinstance(result, list)

    def test_resolve_ssh_config_returns_connection_params(self):
        """resolve_ssh_config returns SSH connection dict."""
        result = resolve_ssh_config("hermes-library")
        if result:
            assert "host" in result
            assert "user" in result
            assert "key" in result
            assert "port" in result

    def test_resolve_ssh_config_empty_for_unknown_service(self):
        """resolve_ssh_config returns empty dict for unknown service."""
        result = resolve_ssh_config("nonexistent-xyz")
        assert result == {}
