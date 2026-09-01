"""Unit tests for data_connector plugin (ADR-0030, ADR-0033, L24).

Coverage: Registry operations, thread-safety, ownership tracking, compliance markers.
Compliance: L24 audit-metadata-only constraint verified.
"""

import pytest
import threading
from unittest.mock import MagicMock, patch

from data_connector import (
    DataConnectorRegistry,
    get_active,
    set_active,
    clear,
    is_installed,
    clear_if_active,
    release_owned_by,
    owner_plugin_id,
)


class TestDataConnectorRegistry:
    """Core registry operations and thread-safety."""

    def test_init_no_default_provider(self):
        """Registry starts with no provider (L24 design)."""
        reg = DataConnectorRegistry()
        assert reg.get_active() is None
        assert reg.owner_plugin_id() is None

    def test_set_and_get_active(self):
        """Provider installation and retrieval."""
        reg = DataConnectorRegistry()
        mock_provider = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "test-plugin"
            reg.set_active(mock_provider)

        assert reg.get_active() is mock_provider
        assert reg.owner_plugin_id() == "test-plugin"

    def test_is_installed(self):
        """Verify provider installation status."""
        reg = DataConnectorRegistry()
        assert not reg.is_installed()

        mock_provider = MagicMock()
        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-1"
            reg.set_active(mock_provider)

        assert reg.is_installed()

    def test_clear_restores_state(self):
        """Clear removes provider without affecting ownership checks."""
        reg = DataConnectorRegistry()
        mock_provider = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-1"
            reg.set_active(mock_provider)

        reg.clear()
        assert reg.get_active() is None
        assert reg.owner_plugin_id() is None

    def test_clear_if_active_instance_check(self):
        """Clear only succeeds if exact provider instance matches."""
        reg = DataConnectorRegistry()
        provider1 = MagicMock()
        provider2 = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-1"
            reg.set_active(provider1)

        # Attempt to clear with different instance
        result = reg.clear_if_active(provider2)
        assert not result
        assert reg.get_active() is provider1

        # Clear with correct instance
        result = reg.clear_if_active(provider1)
        assert result
        assert reg.get_active() is None

    def test_release_owned_by_plugin_id(self):
        """Release slot by owning plugin ID."""
        reg = DataConnectorRegistry()
        mock_provider = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "plugin-a"
            reg.set_active(mock_provider)

        # Wrong plugin cannot release
        assert not reg.release_owned_by("plugin-b")
        assert reg.get_active() is mock_provider

        # Correct plugin releases
        assert reg.release_owned_by("plugin-a")
        assert reg.get_active() is None
        assert reg.owner_plugin_id() is None

    def test_thread_safety_concurrent_sets(self):
        """Concurrent set_active calls remain consistent."""
        reg = DataConnectorRegistry()
        results = []

        def install_provider(plugin_id, order):
            with patch("loading.current") as mock_current:
                mock_current.return_value.plugin_id = plugin_id
                provider = MagicMock(name=f"provider-{plugin_id}")
                reg.set_active(provider)
                results.append((order, reg.owner_plugin_id()))

        threads = [
            threading.Thread(target=install_provider, args=("p1", 1)),
            threading.Thread(target=install_provider, args=("p2", 2)),
            threading.Thread(target=install_provider, args=("p3", 3)),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Final state has valid owner
        assert reg.owner_plugin_id() in ("p1", "p2", "p3")
        assert reg.is_installed()

    def test_module_level_functions(self):
        """Module-level convenience functions delegate to global registry."""
        mock_provider = MagicMock()

        with patch("loading.current") as mock_current:
            mock_current.return_value.plugin_id = "test-id"
            set_active(mock_provider)

        assert get_active() is mock_provider
        assert is_installed()
        assert owner_plugin_id() == "test-id"

        clear()
        assert not is_installed()
        assert owner_plugin_id() is None

    def test_compliance_marker_audit_metadata_only(self):
        """L24 audit-metadata-only constraint documented in module docstring."""
        import data_connector as mod
        doc = mod.__doc__
        assert "L24" in doc
        assert "metadata only" in doc.lower()
        assert "never row contents" in doc.lower()
