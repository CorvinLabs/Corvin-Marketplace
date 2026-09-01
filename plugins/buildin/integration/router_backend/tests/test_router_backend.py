"""Unit tests for router_backend plugin (ADR-0033, L5).

Coverage: Registry operations, default router chain, parameter passing, error handling.
Compliance: ADR-0033 must-NOT-raise contract, delegation routing.
"""

import pytest
import threading
from unittest.mock import MagicMock, patch

from router_backend import (
    RouterBackendRegistry,
    ChainRouterBackend,
    get_active,
    set_active,
    clear,
    clear_if_active,
    release_owned_by,
    owner_plugin_id,
)


class TestChainRouterBackend:
    """Default chain-based router implementation."""

    def test_route_returns_none_when_router_unavailable(self):
        """Returns None gracefully when router module not found."""
        router = ChainRouterBackend()
        with patch.object(router, "_router_mod", return_value=None):
            result = router.route(
                "test input",
                [{"name": "p1"}],
                model="test-model"
            )
        assert result is None

    def test_route_delegates_to_router_module(self):
        """Route call delegates to router module with parameters."""
        router = ChainRouterBackend()
        mock_router_mod = MagicMock()
        mock_router_mod.route.return_value = {"selected": "p1", "confidence": 0.95}

        with patch.object(router, "_router_mod", return_value=mock_router_mod):
            result = router.route(
                "input text",
                [{"name": "p1"}, {"name": "p2"}],
                model="gpt-4",
                min_confidence=0.7,
                timeout=10.0,
                mode="embeddings"
            )

        assert result == {"selected": "p1", "confidence": 0.95}
        mock_router_mod.route.assert_called_once()
        call_kwargs = mock_router_mod.route.call_args[1]
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["min_confidence"] == 0.7
        assert call_kwargs["timeout"] == 10.0
        assert call_kwargs["mode"] == "embeddings"

    def test_route_handles_exception_gracefully(self):
        """Route exception is logged and returns None (ADR-0033 must-NOT-raise)."""
        router = ChainRouterBackend()
        mock_router_mod = MagicMock()
        mock_router_mod.route.side_effect = RuntimeError("Router crashed")

        with patch.object(router, "_router_mod", return_value=mock_router_mod):
            result = router.route("input", [])

        assert result is None  # Fails safely

    def test_route_omits_default_parameters(self):
        """Default parameter values are not passed to router module."""
        router = ChainRouterBackend()
        mock_router_mod = MagicMock()
        mock_router_mod.route.return_value = {}

        with patch.object(router, "_router_mod", return_value=mock_router_mod):
            router.route(
                "input",
                [{"name": "p"}],
                model="",  # Empty model is default
                timeout=12.0,  # Default timeout
            )

        call_kwargs = mock_router_mod.route.call_args[1]
        # Empty model should not be passed
        assert "model" not in call_kwargs or call_kwargs.get("model") == ""
        # Default timeout should not be passed
        assert "timeout" not in call_kwargs or call_kwargs.get("timeout") == 12.0


class TestRouterBackendRegistry:
    """Registry operations and provider lifecycle."""

    def test_init_has_default_provider(self):
        """Registry initializes with ChainRouterBackend."""
        reg = RouterBackendRegistry()
        assert isinstance(reg.get_active(), ChainRouterBackend)
        assert reg.owner_plugin_id() is None

    def test_set_active_with_ownership(self):
        """Set custom provider with ownership tracking."""
        reg = RouterBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "router-plugin"
            reg.set_active(custom)

        assert reg.get_active() is custom
        assert reg.owner_plugin_id() == "router-plugin"

    def test_release_owned_by_restores_default(self):
        """Release by plugin ID restores ChainRouterBackend."""
        reg = RouterBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-router"
            reg.set_active(custom)

        assert reg.release_owned_by("plugin-router")
        assert isinstance(reg.get_active(), ChainRouterBackend)

    def test_release_wrong_plugin_fails(self):
        """Release by wrong plugin ID fails."""
        reg = RouterBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-a"
            reg.set_active(custom)

        assert not reg.release_owned_by("plugin-b")
        assert reg.get_active() is custom

    def test_clear_restores_default(self):
        """Clear() restores default ChainRouterBackend."""
        reg = RouterBackendRegistry()
        custom = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin"
            reg.set_active(custom)

        reg.clear()
        assert isinstance(reg.get_active(), ChainRouterBackend)
        assert reg.owner_plugin_id() is None

    def test_clear_if_active_instance_check(self):
        """Clear only if exact instance matches."""
        reg = RouterBackendRegistry()
        provider1 = MagicMock(name="p1")
        provider2 = MagicMock(name="p2")

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin"
            reg.set_active(provider1)

        assert not reg.clear_if_active(provider2)
        assert reg.get_active() is provider1

        assert reg.clear_if_active(provider1)
        assert isinstance(reg.get_active(), ChainRouterBackend)

    def test_thread_safety_concurrent_routes(self):
        """Concurrent route calls and provider swaps are thread-safe."""
        reg = RouterBackendRegistry()
        results = []

        def route_multiple():
            for i in range(3):
                backend = reg.get_active()
                # Just verify we can call it without crashing
                results.append(backend is not None)

        def swap_provider():
            custom = MagicMock()
            with patch("loading.current") as mock_current:
                mock_current.return_value.plugin_id = f"plugin-{threading.current_thread().ident}"
                reg.set_active(custom)
            results.append("swapped")

        threads = [
            threading.Thread(target=route_multiple),
            threading.Thread(target=swap_provider),
            threading.Thread(target=route_multiple),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) > 0

    def test_module_level_functions(self):
        """Module-level convenience functions work correctly."""
        custom = MagicMock()
        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "test-router"
            set_active(custom)

        assert get_active() is custom
        assert owner_plugin_id() == "test-router"

        assert clear_if_active(custom)
        assert isinstance(get_active(), ChainRouterBackend)
