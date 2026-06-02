"""
tests/test_aether_core.py
Unit tests for Aether Core's routing and streaming firewall pipeline.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from core.aether_core import AetherCore, Request, Response
from core.security import RoutingDecision


class TestAetherCoreRouting:
    @patch("core.aether_core.get_provider_manager")
    @patch("core.aether_core.ensure_registry_initialized")
    def test_route_request_blocked(self, mock_ensure, mock_get_pm):
        # Setup mocks
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        core = AetherCore()
        core.initialize()

        # Mock the firewall to block
        core.firewall = MagicMock()
        mock_scan_result = MagicMock()
        mock_scan_result.is_clean = False
        core.firewall.scan_and_route.return_value = (RoutingDecision.BLOCKED, mock_scan_result)

        request = Request(prompt="DROP TABLE users;")
        response = core.route_request(request)

        assert response.success is False
        assert response.firewall_status == "blocked"
        assert response.routing_decision == "blocked"
        mock_pm.call_with_failover.assert_not_called()

    @patch("core.aether_core.get_provider_manager")
    @patch("core.aether_core.ensure_registry_initialized")
    def test_route_request_local(self, mock_ensure, mock_get_pm):
        # Setup mocks
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm
        mock_provider_response = MagicMock()
        mock_provider_response.success = True
        mock_provider_response.content = "local reply"
        mock_provider_response.provider = "local"
        mock_provider_response.model = "local-model"
        mock_provider_response.metadata = {}
        mock_pm.call_with_failover.return_value = mock_provider_response

        core = AetherCore()
        core.initialize()

        # Mock the firewall to route local
        core.firewall = MagicMock()
        mock_scan_result = MagicMock()
        mock_scan_result.is_clean = False
        core.firewall.scan_and_route.return_value = (RoutingDecision.LOCAL, mock_scan_result)

        request = Request(prompt="execute script")
        response = core.route_request(request)

        assert response.success is True
        assert response.content == "local reply"
        assert response.provider == "local"
        # Check call_with_failover was called with local_only=True
        mock_pm.call_with_failover.assert_called_once()
        kwargs = mock_pm.call_with_failover.call_args[1]
        assert kwargs.get("local_only") is True

    @patch("core.aether_core.get_provider_manager")
    @patch("core.aether_core.ensure_registry_initialized")
    def test_route_stream_blocked(self, mock_ensure, mock_get_pm):
        # Setup mocks
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm

        core = AetherCore()
        core.initialize()

        # Mock the firewall to block
        core.firewall = MagicMock()
        mock_scan_result = MagicMock()
        mock_scan_result.is_clean = False
        core.firewall.scan_and_route.return_value = (RoutingDecision.BLOCKED, mock_scan_result)

        request = Request(prompt="DROP TABLE users;")
        chunks = list(core.route_stream(request))

        assert len(chunks) == 1
        assert "Request blocked by Intelligence Firewall" in chunks[0]
        mock_pm.call_with_failover_stream.assert_not_called()

    @patch("core.aether_core.get_provider_manager")
    @patch("core.aether_core.ensure_registry_initialized")
    def test_route_stream_local(self, mock_ensure, mock_get_pm):
        # Setup mocks
        mock_pm = MagicMock()
        mock_get_pm.return_value = mock_pm
        mock_pm.call_with_failover_stream.return_value = iter(["local", " stream"])

        core = AetherCore()
        core.initialize()

        # Mock the firewall to route local
        core.firewall = MagicMock()
        mock_scan_result = MagicMock()
        mock_scan_result.is_clean = False
        core.firewall.scan_and_route.return_value = (RoutingDecision.LOCAL, mock_scan_result)

        request = Request(prompt="execute script")
        chunks = list(core.route_stream(request))

        assert chunks == ["local", " stream"]
        mock_pm.call_with_failover_stream.assert_called_once()
        kwargs = mock_pm.call_with_failover_stream.call_args[1]
        assert kwargs.get("local_only") is True
